"""Tests for rt_plugin — config I/O and the RT REST 2.0 client.

RT is never contacted: ``requests.Session`` is replaced with a fake whose handler
returns canned REST 2.0 payloads, and Drive read/write go through an in-memory
transport. We exercise config validation, ticket/history normalization, pagination,
the write-through actions, and the error mapping.
"""

import base64
import json

import pytest
from cryptography.fernet import Fernet

import plugin_common
import rt_plugin

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeResp:
    def __init__(self, status=200, json_data=None, text="", raise_json=False):
        self.status_code = status
        self._json = json_data
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._json


class FakeSession:
    """Stands in for requests.Session; routes every call through ``handler``."""

    def __init__(self, handler):
        self.headers = {}
        self.auth = None
        self.handler = handler
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)


@pytest.fixture
def fake_rt(monkeypatch):
    """Install a FakeSession whose handler the test sets via ``fake_rt.handler = ...``.

    Returns an object exposing ``.session`` (the last session built) and ``.handler``.
    """

    holder = {"handler": lambda m, u, k: FakeResp(json_data={}), "session": None}

    def make_session():
        holder["session"] = FakeSession(lambda m, u, k: holder["handler"](m, u, k))
        return holder["session"]

    monkeypatch.setattr(rt_plugin.requests, "Session", make_session)
    # Client-behaviour tests use the default base_url host "rt-internal"; allowlist it
    # so the destination check passes without real DNS. SSRF tests override this env.
    monkeypatch.setenv("RT_ALLOWED_HOSTS", "rt-internal")

    class Access:
        @property
        def session(self):
            return holder["session"]

        @session.setter
        def session(self, _v):
            pass

        @property
        def handler(self):
            return holder["handler"]

        @handler.setter
        def handler(self, fn):
            holder["handler"] = fn

    return Access()


def _cfg(**over):
    base = {
        "base_url": "http://rt-internal",
        "public_url": "https://rt.example.com",
        "rest_token": "",
        "basic_user": "scott",
        "basic_pass": "pw",
        "query": rt_plugin.DEFAULT_QUERY,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


class TestValidateConfig:
    def test_defaults_blank_query(self):
        clean = rt_plugin.validate_config({"base_url": "http://x", "query": "   "})
        assert clean["query"] == rt_plugin.DEFAULT_QUERY

    def test_strips_plain_fields_but_not_query(self):
        clean = rt_plugin.validate_config({"base_url": "  http://x  ", "query": "  id = 1  "})
        assert clean["base_url"] == "http://x"
        assert (
            clean["query"] == "  id = 1  "
        )  # query preserved verbatim (TicketSQL is whitespace-tolerant but user-owned)

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            rt_plugin.validate_config({"base_url": 123})

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            rt_plugin.validate_config(["nope"])

    def test_unknown_fields_dropped(self):
        clean = rt_plugin.validate_config({"base_url": "http://x", "evil": "y"})
        assert "evil" not in clean


class TestUrlScheme:
    def test_bare_host_gets_https(self):
        clean = rt_plugin.validate_config({"base_url": "rt.example.com/", "public_url": "rt.example.com"})
        assert clean["base_url"] == "https://rt.example.com/"
        assert clean["public_url"] == "https://rt.example.com"

    def test_explicit_scheme_kept(self):
        assert rt_plugin.validate_config({"base_url": "http://10.0.0.5:8080"})["base_url"] == "http://10.0.0.5:8080"

    def test_scheme_only_counts_at_start(self):
        clean = rt_plugin.validate_config({"base_url": "rt.example.com/?next=https://other"})
        assert clean["base_url"] == "https://rt.example.com/?next=https://other"

    def test_empty_stays_empty(self):
        assert rt_plugin.validate_config({"base_url": ""})["base_url"] == ""


class TestConnectable:
    def test_needs_base_and_auth(self):
        assert rt_plugin.config_is_connectable(_cfg()) is True
        assert rt_plugin.config_is_connectable(_cfg(basic_user="", rest_token="")) is False
        assert rt_plugin.config_is_connectable(_cfg(base_url="")) is False
        assert rt_plugin.config_is_connectable(_cfg(basic_user="", rest_token="tok")) is True


class TestConfigRoundtrip:
    @pytest.fixture
    def drive(self, monkeypatch):
        store = {}

        class FakeTransport:
            def __init__(self, service, folder_id):
                pass

            def download_file(self, name):
                return store.get(name)

            def upload_file(self, name, content):
                store[name] = content

        monkeypatch.setattr(plugin_common, "config_transport", lambda s, f, plugin_id: FakeTransport(s, f))
        # Seal key for at-rest secret encryption (shared with the MCP process in prod).
        monkeypatch.setenv("MCP_TOKEN_SEAL_KEY", Fernet.generate_key().decode())
        return store

    def test_read_missing_returns_defaults(self, drive):
        cfg = rt_plugin.read_config(None, "folder")
        assert cfg == rt_plugin._empty_config()

    def test_write_then_read(self, drive):
        rt_plugin.write_config(None, "folder", _cfg(base_url="http://rt", basic_user="u"))
        cfg = rt_plugin.read_config(None, "folder")
        assert cfg["base_url"] == "http://rt"
        assert cfg["basic_user"] == "u"

    def test_read_corrupt_returns_defaults(self, drive):
        drive[rt_plugin.CONFIG_FILE] = "{not json"
        assert rt_plugin.read_config(None, "folder") == rt_plugin._empty_config()

    def test_secrets_encrypted_at_rest(self, drive):
        rt_plugin.write_config(
            None, "folder", _cfg(base_url="http://rt", basic_pass="supersecret", rest_token="tok123")
        )
        raw = drive[rt_plugin.CONFIG_FILE]
        assert "supersecret" not in raw and "tok123" not in raw
        stored = json.loads(raw)
        assert stored["basic_pass"].startswith("fernet:")
        assert stored["rest_token"].startswith("fernet:")
        # read_config transparently decrypts
        cfg = rt_plugin.read_config(None, "folder")
        assert cfg["basic_pass"] == "supersecret"
        assert cfg["rest_token"] == "tok123"

    def test_update_preserves_unentered_secrets(self, drive):
        rt_plugin.write_config(None, "folder", _cfg(base_url="http://rt", rest_token="tok123"))
        clean = rt_plugin.update_config(None, "folder", {"base_url": "http://rt2", "rest_token": "", "query": None})
        assert clean["base_url"] == "http://rt2"
        assert clean["rest_token"] == "tok123"
        assert rt_plugin.read_config(None, "folder")["rest_token"] == "tok123"

    def test_public_config_masks_secrets(self, drive):
        public = rt_plugin.public_config(_cfg(base_url="http://rt", basic_pass="pw", rest_token=""))
        assert "basic_pass" not in public and "rest_token" not in public
        assert public["has_basic_pass"] is True and public["has_rest_token"] is False


class TestConfigMcpTools:
    @pytest.fixture
    def tools(self, monkeypatch):
        store = {"cfg": _cfg(base_url="http://rt", rest_token="tok")}
        monkeypatch.setattr(rt_plugin, "read_config", lambda s, f: dict(store["cfg"]))

        def fake_write(_s, _f, cfg):
            store["cfg"] = rt_plugin.validate_config(cfg)
            return store["cfg"]

        monkeypatch.setattr(rt_plugin, "write_config", fake_write)
        captured = {}

        class FakeMCP:
            def tool(self):
                def deco(fn):
                    captured[fn.__name__] = fn
                    return fn

                return deco

        rt_plugin.register_mcp_tools(FakeMCP(), lambda: {"service": None, "folder_id": "f"})
        return captured, store

    def test_get_never_returns_secrets(self, tools):
        t, _ = tools
        result = t["get_rt_config"]()
        assert "tok" not in result.values()
        assert result["has_rest_token"] is True

    def test_set_merges_and_masks(self, tools):
        t, store = tools
        result = t["set_rt_config"](basic_user="scott", basic_pass="pw")
        assert result["basic_user"] == "scott" and result["has_basic_pass"] is True
        assert "pw" not in result.values()
        assert store["cfg"]["rest_token"] == "tok"
        assert store["cfg"]["base_url"] == "http://rt"

    def test_connection_goes_through_destination_guard(self, tools, monkeypatch):
        t, _ = tools
        monkeypatch.delenv("RT_ALLOWED_HOSTS", raising=False)
        t["set_rt_config"](base_url="http://127.0.0.1:8080")
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError, match="non-public|http"):
            t["test_rt_connection"]()

    def test_tickets_carry_deep_links(self, tools, monkeypatch):
        t, _ = tools
        monkeypatch.setenv("ACQUACOTTA_PUBLIC_URL", "https://acq.example.com")
        monkeypatch.setattr(rt_plugin, "fetch_tickets", lambda cfg, query=None: [{"id": "1529", "subject": "S"}])
        monkeypatch.setattr(rt_plugin, "fetch_ticket_history", lambda cfg, tid: [])
        assert t["list_tickets"]()[0]["link"] == "https://acq.example.com/#rt/ticket/1529"
        assert t["get_ticket"]("1529")["ticket"]["link"] == "https://acq.example.com/#rt/ticket/1529"

    def test_get_ticket_rejects_bad_id(self, tools):
        from fastmcp.exceptions import ToolError

        t, _ = tools
        with pytest.raises(ToolError):
            t["get_ticket"]("1 OR 1=1")


# --------------------------------------------------------------------------- #
# Session / auth selection
# --------------------------------------------------------------------------- #


class TestSession:
    def test_basic_auth_preferred(self, fake_rt):
        s = rt_plugin._session(_cfg(basic_user="scott", rest_token="tok"))
        assert s.auth == ("scott", "pw")
        assert "Authorization" not in s.headers

    def test_token_when_no_basic(self, fake_rt):
        s = rt_plugin._session(_cfg(basic_user="", basic_pass="", rest_token="tok"))
        assert s.auth is None
        assert s.headers["Authorization"] == "token tok"

    def test_requires_some_auth(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin._session(_cfg(basic_user="", rest_token=""))


# --------------------------------------------------------------------------- #
# Tickets
# --------------------------------------------------------------------------- #


class TestFetchTickets:
    def test_normalizes_nested_records(self, fake_rt):
        def handler(method, url, kw):
            return FakeResp(
                json_data={
                    "items": [
                        {
                            "id": 42,
                            "Subject": "Fix the thing",
                            "Status": "open",
                            "Queue": {"id": "3", "Name": "Professional", "type": "queue"},
                            "Owner": {"id": "7", "Name": "scott", "type": "user"},
                            "Requestor": [{"id": "1", "Name": "a@b.com", "type": "user"}],
                            "Priority": 0,
                            "Created": "2026-10-01T00:00:00Z",
                            "LastUpdated": "2026-10-10T00:00:00Z",
                            "Due": "",
                        }
                    ],
                    "pages": 1,
                }
            )

        fake_rt.handler = handler
        tickets = rt_plugin.fetch_tickets(_cfg())
        assert len(tickets) == 1
        t = tickets[0]
        assert t["id"] == "42"
        assert t["queue"] == "Professional"
        assert t["owner"] == "scott"
        assert t["requestors"] == "a@b.com"
        assert t["url"] == "https://rt.example.com/Ticket/Display.html?id=42"

    def test_paginates_by_page_number(self, fake_rt):
        # Pages are requested by incrementing ?page=N against our own URL; the
        # response's next_page URL is never followed.
        def handler(method, url, kw):
            page = (kw.get("params") or {}).get("page", 1)
            if page == 1:
                return FakeResp(
                    json_data={
                        "items": [{"id": 1, "Queue": {"Name": "Q"}}],
                        "pages": 2,
                        "next_page": "http://evil.example/REST/2.0/tickets",
                    }
                )
            return FakeResp(json_data={"items": [{"id": 2, "Queue": {"Name": "Q"}}], "pages": 2})

        fake_rt.handler = handler
        tickets = rt_plugin.fetch_tickets(_cfg())
        assert [t["id"] for t in tickets] == ["1", "2"]
        # Every request went to our own tickets endpoint, never the injected host.
        assert all("evil.example" not in call[1] for call in fake_rt.session.calls)

    def test_url_omitted_without_public_base(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": [{"id": 9}], "pages": 1})
        tickets = rt_plugin.fetch_tickets(_cfg(public_url="", base_url="http://rt-internal"))
        # falls back to base_url for the link
        assert tickets[0]["url"] == "http://rt-internal/Ticket/Display.html?id=9"


class TestFetchTicket:
    def test_queries_by_id_not_the_configured_query(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": [{"id": 1529, "Subject": "S"}], "pages": 1})
        ticket = rt_plugin.fetch_ticket(_cfg(query="Owner = '__CurrentUser__'"), "1529")
        assert ticket["id"] == "1529"
        assert fake_rt.session.calls[0][2]["params"]["query"] == "id = 1529"

    def test_missing_ticket_is_none(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": [], "pages": 1})
        assert rt_plugin.fetch_ticket(_cfg(), "7") is None

    @pytest.mark.parametrize("bad", ["", "1 OR 1=1", "abc", "-1"])
    def test_rejects_non_numeric_id(self, fake_rt, bad):
        with pytest.raises(ValueError):
            rt_plugin.fetch_ticket(_cfg(), bad)


class TestErrors:
    def test_non_json_raises(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(text="<html>login</html>", raise_json=True)
        with pytest.raises(rt_plugin.RTError):
            rt_plugin.test_connection(_cfg())

    def test_401_raises(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(status=401, json_data={})
        with pytest.raises(rt_plugin.RTError):
            rt_plugin.fetch_tickets(_cfg())

    def test_network_error_raises(self, fake_rt):
        def boom(method, url, kw):
            raise rt_plugin.requests.RequestException("conn refused")

        fake_rt.handler = boom
        with pytest.raises(rt_plugin.RTError):
            rt_plugin.fetch_tickets(_cfg())

    def test_missing_base_url_is_value_error(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin.fetch_tickets(_cfg(base_url=""))


class TestTestConnection:
    def test_returns_version(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"Version": "6.0.2"})
        assert rt_plugin.test_connection(_cfg())["version"] == "6.0.2"


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #


class TestHistory:
    def test_rejects_bad_id(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin.fetch_ticket_history(_cfg(), "1; DROP")

    def test_normalizes_and_fetches_content(self, fake_rt):
        def handler(method, url, kw):
            if "/history" in url:
                return FakeResp(
                    json_data={
                        "items": [
                            {
                                "id": 100,
                                "Type": "Correspond",
                                "Creator": {"Name": "scott"},
                                "Created": "2026-10-10T00:00:00Z",
                                "Description": "Correspondence added",
                                # RT 6's real shape: attachment links have a _url, no id.
                                "_hyperlinks": [
                                    {"ref": "self", "id": 100, "type": "transaction"},
                                    {"ref": "attachment", "_url": "https://rt.example.com/REST/2.0/attachment/500"},
                                ],
                            }
                        ],
                        "pages": 1,
                    }
                )
            if "/attachment/500" in url:
                return FakeResp(json_data={"Content": base64.b64encode(b"Hello there").decode()})
            return FakeResp(json_data={})

        fake_rt.handler = handler
        hist = rt_plugin.fetch_ticket_history(_cfg(), "42")
        assert hist[0]["type"] == "Correspond"
        assert hist[0]["creator"] == "scott"
        assert hist[0]["content"] == "Hello there"

    def test_create_transaction_gets_opening_body(self, fake_rt):
        def handler(method, url, kw):
            if "/history" in url:
                item = {
                    "id": 1,
                    "Type": "Create",
                    "Created": "x",
                    "_hyperlinks": [{"ref": "attachment", "_url": "https://rt.example.com/REST/2.0/attachment/7"}],
                }
                return FakeResp(json_data={"items": [item], "pages": 1})
            if "/attachment/7" in url:
                return FakeResp(json_data={"Content": base64.b64encode(b"Opening message").decode()})
            return FakeResp(json_data={})

        fake_rt.handler = handler
        assert rt_plugin.fetch_ticket_history(_cfg(), "42")[0]["content"] == "Opening message"

    def test_limits_transactions(self, fake_rt, monkeypatch):
        monkeypatch.setattr(rt_plugin, "_HISTORY_LIMIT", 2)
        items = [{"id": i, "Type": "Status", "Created": "x"} for i in range(10)]
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": items, "pages": 1})
        hist = rt_plugin.fetch_ticket_history(_cfg(), "42")
        assert len(hist) == 2


# --------------------------------------------------------------------------- #
# Write-through actions
# --------------------------------------------------------------------------- #


class TestActions:
    def test_reply_posts_correspond(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data=["Correspondence added"])
        rt_plugin.act_on_ticket(_cfg(), "42", "reply", "my reply")
        method, url, kw = fake_rt.session.calls[0]
        assert method == "POST"
        assert url.endswith("/ticket/42/correspond")
        assert kw["json"]["Content"] == "my reply"

    def test_comment_posts_comment(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data=["Comments added"])
        rt_plugin.act_on_ticket(_cfg(), "42", "comment", "internal note")
        _m, url, _k = fake_rt.session.calls[0]
        assert url.endswith("/ticket/42/comment")

    def test_status_puts_ticket(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(json_data=["Status changed"])
        rt_plugin.act_on_ticket(_cfg(), "42", "status", "resolved")
        method, url, kw = fake_rt.session.calls[0]
        assert method == "PUT"
        assert url.endswith("/ticket/42")
        assert kw["json"]["Status"] == "resolved"

    def test_rejects_blank_value(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin.act_on_ticket(_cfg(), "42", "reply", "   ")

    def test_rejects_bad_id(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin.act_on_ticket(_cfg(), "nan", "status", "open")

    def test_rejects_unknown_action(self, fake_rt):
        with pytest.raises(ValueError):
            rt_plugin.act_on_ticket(_cfg(), "42", "delete", "x")


class TestDestinationAllowlist:
    def test_blocks_host_not_in_allowlist(self, fake_rt, monkeypatch):
        monkeypatch.setenv("RT_ALLOWED_HOSTS", "rt-internal,rt.example.com")
        with pytest.raises(ValueError):
            rt_plugin.fetch_tickets(_cfg(base_url="http://169.254.169.254"))

    def test_allowlist_permits_internal_host(self, fake_rt, monkeypatch):
        # An operator-allowlisted host is trusted even if it's a private/internal name.
        monkeypatch.setenv("RT_ALLOWED_HOSTS", "rt-internal")
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": [], "pages": 1})
        assert rt_plugin.fetch_tickets(_cfg(base_url="http://rt-internal")) == []

    def test_no_allowlist_permits_public(self, fake_rt, monkeypatch):
        monkeypatch.delenv("RT_ALLOWED_HOSTS", raising=False)
        fake_rt.handler = lambda m, u, k: FakeResp(json_data={"items": [], "pages": 1})
        assert rt_plugin.fetch_tickets(_cfg(base_url="http://93.184.216.34")) == []

    def test_no_allowlist_blocks_private(self, fake_rt, monkeypatch):
        monkeypatch.delenv("RT_ALLOWED_HOSTS", raising=False)
        with pytest.raises(ValueError):
            rt_plugin.fetch_tickets(_cfg(base_url="http://10.0.0.5"))

    def test_no_allowlist_blocks_loopback(self, fake_rt, monkeypatch):
        monkeypatch.delenv("RT_ALLOWED_HOSTS", raising=False)
        with pytest.raises(ValueError):
            rt_plugin.fetch_tickets(_cfg(base_url="http://127.0.0.1"))

    def test_rejects_non_http_scheme(self, fake_rt, monkeypatch):
        monkeypatch.delenv("RT_ALLOWED_HOSTS", raising=False)
        with pytest.raises(ValueError):
            rt_plugin.fetch_tickets(_cfg(base_url="ftp://rt-internal"))


class TestTicketIdSafety:
    def test_non_numeric_ticket_dropped(self, fake_rt):
        fake_rt.handler = lambda m, u, k: FakeResp(
            json_data={"items": [{"id": "1'); evil"}, {"id": 7, "Queue": {"Name": "Q"}}], "pages": 1}
        )
        tickets = rt_plugin.fetch_tickets(_cfg())
        assert [t["id"] for t in tickets] == ["7"]
