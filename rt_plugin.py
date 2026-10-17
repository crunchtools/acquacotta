"""Acquacotta RT Tickets Plugin — your Request Tracker tickets, in Acquacotta.

Unlike Todos/Discussions (where the browser owns the data and the user's Google
Drive is the source of truth), **RT itself is the source of truth** here. This
plugin is a read-through proxy + write-through actions mirror:

* Reads go server -> RT REST 2.0 -> browser (cached in IndexedDB for offline).
* Writes (reply / comment / status) go browser -> server -> RT.
* The only thing persisted to the user's Drive is the *connection config*
  (``plugins/rt/config.json``): the RT base URL, auth, and the ticket search.
  No credential is ever stored on the server — it is read per request from the
  user's own Drive, used in memory to call RT, and discarded.

The plugin is deliberately instance-agnostic: point ``base_url`` at any RT 5+/6.x
instance. A deployment that fronts RT with an auth proxy (e.g. Cloudflare Access)
simply configures ``base_url`` at RT's private address so the server reaches it
directly; ``public_url`` is the browser-facing link used for clickable tickets.

Auth to RT is single-header by nature (HTTP allows one ``Authorization``), so the
client uses exactly one mode: HTTP Basic when ``basic_user`` is set (the common
case when RT's Apache gates everything and maps REMOTE_USER into RT), otherwise an
RT REST 2.0 token (``Authorization: token <t>``).
"""

import base64
import ipaddress
import json
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken

import mcp_tokens
from transports.google_drive_transport import GoogleDriveTransport

# RT ticket and transaction ids are integers. The sync boundary enforces this so a
# crafted id can never reach the frontend, where ids are interpolated into HTML
# attributes and inline handlers (same trust-boundary reasoning as the UUID check
# in discussions_plugin).
_TICKET_ID_RE = re.compile(r"\A[0-9]+\Z")

PLUGIN_METADATA = {
    "id": "rt",
    "name": "RT Tickets",
    "description": "Your Request Tracker tickets, grouped by queue, with the full history thread",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "has_tab": True,
    "tab_label": "Tickets",
    "tab_id": "rt",
    "has_counts": True,
    "has_sync": True,
    "has_import_export": False,
}

CONFIG_FILE = "config.json"
PLUGIN_FOLDER = "plugins/rt"

# Default TicketSQL: the tickets I own that are still open. RT expands
# ``__CurrentUser__`` to the authenticated user, so the default needs no hardcoded
# name and travels to any instance. Fully editable in the plugin's settings.
DEFAULT_QUERY = "Owner = '__CurrentUser__' AND Status != 'resolved' AND Status != 'rejected' AND Status != 'deleted'"

# Fields requested from RT for the ticket list. Queue/Owner are RT records; ask RT
# to inline their Name so we get a flat string without a follow-up fetch.
_TICKET_FIELDS = "Subject,Status,Queue,Owner,Requestor,Priority,Created,LastUpdated,Due"
_TICKET_SUBFIELDS = {"fields[Queue]": "Name", "fields[Owner]": "Name"}

# How many history transactions to render, newest first. RT tickets can have
# hundreds of transactions; the thread view wants the recent conversation, not an
# audit dump. Editable constant rather than config — a sane cap, not a preference.
_HISTORY_LIMIT = 50

# Cap per-transaction attachment fetches for one history load. Each correspondence/
# comment body is a separate RT request, so this bounds the round trips (and
# latency) of opening a long-threaded ticket; the fetches run concurrently.
_CONTENT_FETCH_LIMIT = 20
_CONTENT_FETCH_WORKERS = 5

# Upper bound on tickets returned for one query, so a broad user TicketSQL can't
# produce an unbounded response / memory spike.
_MAX_TICKETS = 500

_HTTP_TIMEOUT = 20  # seconds, per RT request

# RT secret fields are encrypted at rest in the user's Drive (constitution:
# credentials are not persisted in the clear). Values are stored as
# ``fernet:<token>`` using the server seal key shared with the MCP process.
_ENC_PREFIX = "fernet:"
_SECRET_CONFIG_FIELDS = ("basic_pass", "rest_token")


class RTError(Exception):
    """An RT request failed (network, auth, or HTTP error from RT itself).

    Distinct from ValueError (bad local input/config): routes map RTError to a 502
    (upstream problem) and ValueError to a 400 (caller's problem).
    """


# --------------------------------------------------------------------------- #
# Per-user connection config, stored in the user's own Google Drive.
# --------------------------------------------------------------------------- #

_CONFIG_FIELDS = ("base_url", "public_url", "rest_token", "basic_user", "basic_pass", "query")


def _empty_config():
    """A fresh, fully-defaulted config. Never share one instance."""
    return {
        "base_url": "",
        "public_url": "",
        "rest_token": "",
        "basic_user": "",
        "basic_pass": "",
        "query": DEFAULT_QUERY,
    }


def _encrypt_secret(value):
    """Encrypt a secret for at-rest storage in the user's Drive, or '' for empty."""
    if not value:
        return ""
    return _ENC_PREFIX + Fernet(mcp_tokens._seal_key()).encrypt(value.encode()).decode()


def _decrypt_secret(value):
    """Decrypt a stored secret. Returns '' if the seal key has rotated (the user
    re-enters it) and passes through any legacy plaintext value unchanged."""
    if not value or not value.startswith(_ENC_PREFIX):
        return value or ""
    try:
        return Fernet(mcp_tokens._seal_key()).decrypt(value[len(_ENC_PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""


def _ensure_plugin_folder(drive_service, folder_id):
    """Ensure plugins/rt/ subfolder exists under the user's root, return its folder ID."""
    plugins_id = _find_or_create_folder(drive_service, folder_id, "plugins")
    return _find_or_create_folder(drive_service, plugins_id, "rt")


def _find_or_create_folder(service, parent_id, name):
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def read_config(drive_service, folder_id):
    """Read the user's RT connection config from their Google Drive.

    Returns a fully-defaulted config dict (see ``_empty_config``) merged with
    whatever is stored, so missing keys always have safe defaults. A missing,
    empty, or malformed file degrades to the all-defaults config rather than
    raising.
    """
    rt_folder_id = _ensure_plugin_folder(drive_service, folder_id)
    rt_transport = GoogleDriveTransport(drive_service, rt_folder_id)
    content = rt_transport.download_file(CONFIG_FILE)
    config = _empty_config()
    if content is None:
        return config
    try:
        stored = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return config
    if not isinstance(stored, dict):
        return config
    for field in _CONFIG_FIELDS:
        if isinstance(stored.get(field), str):
            config[field] = stored[field]
    for field in _SECRET_CONFIG_FIELDS:
        config[field] = _decrypt_secret(config[field])
    if not config["query"].strip():
        config["query"] = DEFAULT_QUERY
    return config


def write_config(drive_service, folder_id, config):
    """Persist the user's RT connection config to their Google Drive (full replace).

    ``config`` is normalized through ``validate_config`` first, so only the known
    string fields are written and the file shape is always clean.
    """
    clean = validate_config(config)
    rt_folder_id = _ensure_plugin_folder(drive_service, folder_id)
    rt_transport = GoogleDriveTransport(drive_service, rt_folder_id)
    # Encrypt secrets at rest; the plaintext ``clean`` is only returned to the caller
    # (which masks secrets before sending to the browser), never written.
    to_store = dict(clean)
    for field in _SECRET_CONFIG_FIELDS:
        to_store[field] = _encrypt_secret(clean[field])
    rt_transport.upload_file(CONFIG_FILE, json.dumps(to_store, indent=2, ensure_ascii=False))
    return clean


def validate_config(config):
    """Return a clean config dict from caller-supplied input. Raises ValueError on
    a bad shape.

    Only the known fields are kept and each must be a string; the result is always
    a complete, defaulted config so downstream code never has to guard missing keys.
    """
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    clean = _empty_config()
    for field in _CONFIG_FIELDS:
        if field in config and config[field] is not None:
            value = config[field]
            if not isinstance(value, str):
                raise ValueError(f"{field} must be a string")
            clean[field] = value.strip() if field != "query" else value
    if not clean["query"].strip():
        clean["query"] = DEFAULT_QUERY
    return clean


def config_is_connectable(config):
    """True if the config has enough to attempt an RT call (a base URL + some auth)."""
    if not config.get("base_url", "").strip():
        return False
    return bool(config.get("basic_user", "").strip() or config.get("rest_token", "").strip())


# --------------------------------------------------------------------------- #
# RT REST 2.0 client.
# --------------------------------------------------------------------------- #


def _resolved_ips(host):
    """Resolve a host to IP objects (or parse an IP literal). Raises ValueError if
    the name can't be resolved."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return [literal]
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"RT host '{host}' could not be resolved") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _check_destination(base):
    """Guard the server-side proxy against SSRF.

    A user supplies ``base_url`` and the server fetches it, so an unguarded proxy
    would let any authenticated user reach internal services (cloud metadata,
    localhost, 10.x, ...). Policy:

    * ``RT_ALLOWED_HOSTS`` set → the host MUST be listed. The operator has then
      explicitly trusted it, so an internal/private RT address is allowed (this is
      how a deployment reaches RT privately behind an auth proxy).
    * ``RT_ALLOWED_HOSTS`` unset → only public destinations: the scheme must be
      http(s) and the host must not resolve to a loopback/link-local/private/
      reserved address.
    """
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("RT base_url must be an http(s) URL")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("RT base_url has no host")
    allowed_raw = os.environ.get("RT_ALLOWED_HOSTS", "").strip()
    if allowed_raw:
        allowed = {h.strip().lower() for h in allowed_raw.split(",") if h.strip()}
        if host not in allowed:
            raise ValueError(f"RT host '{host}' is not in the RT_ALLOWED_HOSTS allowlist")
        return
    for ip in _resolved_ips(host):
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("RT host resolves to a non-public address — set RT_ALLOWED_HOSTS to allow an internal RT")


def _rest_base(config):
    base = (config.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise ValueError("RT base_url is not configured")
    _check_destination(base)
    return f"{base}/REST/2.0"


def _session(config):
    """Build a requests session carrying exactly one auth mode (see module docstring)."""
    s = requests.Session()
    basic_user = (config.get("basic_user") or "").strip()
    token = (config.get("rest_token") or "").strip()
    if basic_user:
        s.auth = (basic_user, config.get("basic_pass") or "")
    elif token:
        s.headers["Authorization"] = f"token {token}"
    else:
        raise ValueError("RT config needs either a Basic-Auth user or a REST token")
    s.headers["Accept"] = "application/json"
    return s


def _request(session, method, url, **kwargs):
    kwargs.setdefault("timeout", _HTTP_TIMEOUT)
    # Never follow redirects: RT REST returns JSON directly, and a redirect is the
    # signature of an auth proxy in front of RT — following it risks an SSRF bypass.
    kwargs.setdefault("allow_redirects", False)
    try:
        resp = session.request(method, url, **kwargs)
    except requests.RequestException as exc:
        raise RTError(f"Could not reach RT: {exc}") from exc
    if resp.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        raise RTError("RT rejected the credentials (check the Basic-Auth user/token)")
    if resp.status_code >= HTTPStatus.BAD_REQUEST:
        raise RTError(f"RT returned HTTP {resp.status_code}: {resp.text[:300]}")
    return resp


def _json(resp):
    try:
        return resp.json()
    except ValueError as exc:
        # A login redirect (e.g. an auth proxy in front of RT) returns HTML, not
        # JSON — the classic symptom of pointing base_url at the public, gated URL.
        raise RTError(
            "RT did not return JSON — base_url may be pointing at an auth-gated "
            "front end instead of RT's direct address"
        ) from exc


def test_connection(config):
    """Verify the config reaches RT. Returns RT's version string on success.

    Raises ValueError (local config problem) or RTError (RT/network problem).
    """
    session = _session(config)
    resp = _request(session, "GET", f"{_rest_base(config)}/rt")
    rt_info = _json(resp)
    return {"ok": True, "version": rt_info.get("Version", "unknown")}


def _paged_items(session, url, params=None):
    """Yield items across RT's paginated list, requesting pages by number.

    Pages are fetched by incrementing ``page`` against the original URL — we never
    follow the ``next_page`` URL from the response body, so a crafted RT reply can't
    redirect the authenticated session (and its credentials) to another host, nor
    bypass the base-URL allowlist.
    """
    params = dict(params or {})
    params.setdefault("per_page", 100)
    page_num = 1
    while True:
        params["page"] = page_num
        resp = _request(session, "GET", url, params=params)
        page = _json(resp)
        yield from page.get("items", [])
        total_pages = page.get("pages", 1) or 1
        if page_num >= total_pages:
            break
        page_num += 1


def _flat(value):
    """RT inlines linked records as ``{"id":..., "Name":..., "type":...}``; flatten
    to the human string. Pass through plain scalars."""
    if isinstance(value, dict):
        return value.get("Name") or value.get("id") or ""
    if isinstance(value, list):
        return ", ".join(_flat(v) for v in value if _flat(v))
    return value if value is not None else ""


def _ticket_record(item, public_base):
    """Normalize one RT ticket hash into the flat record the UI/MCP consume.

    Returns None for a ticket whose id isn't a plain integer: the id is the trust
    boundary for the frontend (interpolated into attributes/handlers), so a
    non-numeric id from RT is dropped rather than rendered.
    """
    ticket_id = str(item.get("id", "")).strip()
    if not _TICKET_ID_RE.match(ticket_id):
        return None
    public = (public_base or "").rstrip("/")
    return {
        "id": ticket_id,
        "subject": str(item.get("Subject") or ""),
        "status": str(item.get("Status") or ""),
        "queue": str(_flat(item.get("Queue"))),
        "owner": str(_flat(item.get("Owner"))),
        "requestors": str(_flat(item.get("Requestor"))),
        "priority": item.get("Priority"),
        "created": str(item.get("Created") or ""),
        "last_updated": str(item.get("LastUpdated") or ""),
        "due": str(item.get("Due") or ""),
        "url": f"{public}/Ticket/Display.html?id={ticket_id}" if public and ticket_id else "",
    }


def fetch_tickets(config, query=None):
    """Return the tickets matching the config's (or an override) TicketSQL query.

    Each result is a flat record (see ``_ticket_record``). Raises ValueError on a
    local config problem, RTError on an RT/network problem.
    """
    session = _session(config)
    q = (query if query is not None else config.get("query")) or DEFAULT_QUERY
    params = {"query": q, "fields": _TICKET_FIELDS, "orderby": "-LastUpdated", **_TICKET_SUBFIELDS}
    public_base = (config.get("public_url") or config.get("base_url") or "").strip()
    tickets = []
    for item in _paged_items(session, f"{_rest_base(config)}/tickets", params):
        record = _ticket_record(item, public_base)
        if record is not None:
            tickets.append(record)
        if len(tickets) >= _MAX_TICKETS:
            break
    return tickets


def _attachment_text(session, config, attachment_id):
    """Best-effort fetch of a transaction attachment's plaintext content."""
    try:
        resp = _request(
            session, "GET", f"{_rest_base(config)}/attachment/{attachment_id}", params={"fields": "Content"}
        )
        attachment = _json(resp)
    except RTError:
        return ""
    content = attachment.get("Content")
    if not isinstance(content, str) or not content:
        return ""
    # RT returns attachment Content base64-encoded; fall back to raw on decode error.
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return content


def _transaction_base(item):
    """Normalize one history transaction into a record (without its message body)."""
    return {
        "id": str(item.get("id", "")).strip(),
        "type": str(item.get("Type") or ""),
        "creator": str(_flat(item.get("Creator"))),
        "created": str(item.get("Created") or ""),
        "description": str(item.get("Description") or ""),
        "content": "",
    }


def _transaction_content(config, item):
    """Fetch a correspondence/comment transaction's message body (best-effort, '').

    Builds its own session so it is safe to call from a worker thread.
    """
    session = _session(config)
    for att in _hyperlinked_attachments(item):
        text = _attachment_text(session, config, att)
        if text.strip():
            return text
    return ""


def _hyperlinked_attachments(item):
    """Extract attachment ids referenced by a transaction hash."""
    ids = []
    hyperlinks = item.get("_hyperlinks") or []
    for link in hyperlinks:
        if isinstance(link, dict) and link.get("ref") == "attachment" and link.get("id") is not None:
            ids.append(str(link["id"]))
    for att in item.get("Attachments") or []:
        if isinstance(att, dict) and att.get("id") is not None:
            ids.append(str(att["id"]))
    return ids


def fetch_ticket_history(config, ticket_id):
    """Return a ticket's recent history thread, newest first (see ``_HISTORY_LIMIT``).

    Each entry: id, type, creator, created, description, content (message body for
    correspondence/comments, best-effort). Raises ValueError on a bad id/config,
    RTError on an RT/network problem.
    """
    if not _TICKET_ID_RE.match(str(ticket_id)):
        raise ValueError("ticket_id must be a positive integer")
    session = _session(config)
    params = {
        "fields": "Type,Creator,Created,Description,_hyperlinks",
        "fields[Creator]": "Name",
        "orderby": "-Created",
    }
    url = f"{_rest_base(config)}/ticket/{ticket_id}/history"
    items = []
    for item in _paged_items(session, url, params):
        items.append(item)
        if len(items) >= _HISTORY_LIMIT:
            break
    records = [_transaction_base(item) for item in items]
    # Fetch message bodies for the newest correspondence/comments, bounded in count
    # and fetched concurrently so a long thread doesn't serialize dozens of round
    # trips (each body is a separate RT request).
    pending = [(i, items[i]) for i, rec in enumerate(records) if rec["type"] in ("Correspond", "Comment")]
    pending = pending[:_CONTENT_FETCH_LIMIT]
    if pending:
        with ThreadPoolExecutor(max_workers=_CONTENT_FETCH_WORKERS) as pool:
            contents = pool.map(lambda pair: _transaction_content(config, pair[1]), pending)
        for (idx, _item), content in zip(pending, contents, strict=True):
            records[idx]["content"] = content
    return records


def _require_ticket_id(ticket_id):
    if not _TICKET_ID_RE.match(str(ticket_id)):
        raise ValueError("ticket_id must be a positive integer")


# RT endpoints and HTTP verbs for each write action, keyed by the action name the
# UI/MCP use. "reply" is public correspondence; "comment" is internal.
_TICKET_ACTIONS = {
    "reply": ("POST", "correspond"),
    "comment": ("POST", "comment"),
    "status": ("PUT", None),
}


def act_on_ticket(config, ticket_id, action, value):
    """Perform a write action on a ticket and return RT's response.

    Args:
        config: the user's RT connection config.
        ticket_id: the RT ticket number (validated as an integer).
        action: 'reply' (public correspondence), 'comment' (internal note), or
            'status' (change the ticket status).
        value: the message body for 'reply'/'comment', or the new status string for
            'status'. Must be non-blank.

    Raises:
        ValueError: on a bad ticket id, unknown action, or blank value.
        RTError: on an RT/network problem.
    """
    _require_ticket_id(ticket_id)
    if action not in _TICKET_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    if not value or not value.strip():
        raise ValueError(("status" if action == "status" else "content") + " is required")
    method, sub_path = _TICKET_ACTIONS[action]
    base = f"{_rest_base(config)}/ticket/{ticket_id}"
    if action == "status":
        url, body = base, {"Status": value.strip()}
    else:
        url, body = f"{base}/{sub_path}", {"Content": value, "ContentType": "text/plain"}
    return _json(_request(_session(config), method, url, json=body))


# --------------------------------------------------------------------------- #
# MCP tools.
# --------------------------------------------------------------------------- #


def register_mcp_tools(mcp, require_ctx):
    """Register this plugin's MCP tools on a FastMCP instance.

    Called once at startup by the MCP server (via the plugin registry). Defines and
    registers the RT tools as side effects on ``mcp``; returns nothing.

    Args:
        mcp: the FastMCP instance to register the ``@mcp.tool()`` functions on.
        require_ctx: a zero-arg callable the server supplies that authenticates the
            current request and returns the per-request context
            ``{"service", "folder_id", "email"}`` (raising on an invalid token). We
            read that user's RT config from their Drive and act on their behalf; RT
            problems surface as ToolError.

    Returns:
        None.
    """
    from fastmcp.exceptions import ToolError

    def _config(ctx):
        cfg = read_config(ctx["service"], ctx["folder_id"])
        if not config_is_connectable(cfg):
            raise ToolError("RT is not configured — set the connection in Acquacotta's RT settings first")
        return cfg

    @mcp.tool()
    def list_tickets(query: str | None = None) -> list:
        """List the caller's RT tickets.

        Args:
            query: Optional TicketSQL to override the saved search (e.g.
                "Owner = '__CurrentUser__' AND Status = 'open'").

        Returns:
            A list of ticket records: id, subject, status, queue, owner, requestors,
            priority, created, last_updated, due, url.
        """
        ctx = require_ctx()
        try:
            return fetch_tickets(_config(ctx), query=query)
        except (ValueError, RTError) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def get_ticket(ticket_id: str) -> dict:
        """Get one ticket plus its recent history thread.

        Args:
            ticket_id: The RT ticket number.

        Returns:
            ``{"ticket": <record>, "history": [<transaction>, ...]}`` where each
            transaction has id, type, creator, created, description, and content
            (message body for correspondence/comments).
        """
        ctx = require_ctx()
        cfg = _config(ctx)
        try:
            tickets = fetch_tickets(cfg, query=f"id = {int(ticket_id)}")
            history = fetch_ticket_history(cfg, ticket_id)
        except (ValueError, RTError) as exc:
            raise ToolError(str(exc)) from exc
        return {"ticket": tickets[0] if tickets else None, "history": history}

    @mcp.tool()
    def reply_ticket_tool(ticket_id: str, content: str) -> dict:
        """Add public correspondence (a reply, sent to requestors) to a ticket."""
        ctx = require_ctx()
        try:
            act_on_ticket(_config(ctx), ticket_id, "reply", content)
        except (ValueError, RTError) as exc:
            raise ToolError(str(exc)) from exc
        return {"status": "ok", "ticket_id": str(ticket_id), "action": "reply"}

    @mcp.tool()
    def comment_ticket_tool(ticket_id: str, content: str) -> dict:
        """Add an internal comment (not sent to requestors) to a ticket."""
        ctx = require_ctx()
        try:
            act_on_ticket(_config(ctx), ticket_id, "comment", content)
        except (ValueError, RTError) as exc:
            raise ToolError(str(exc)) from exc
        return {"status": "ok", "ticket_id": str(ticket_id), "action": "comment"}

    @mcp.tool()
    def set_ticket_status_tool(ticket_id: str, status: str) -> dict:
        """Change a ticket's status (e.g. 'open', 'stalled', 'resolved')."""
        ctx = require_ctx()
        try:
            act_on_ticket(_config(ctx), ticket_id, "status", status)
        except (ValueError, RTError) as exc:
            raise ToolError(str(exc)) from exc
        return {"status": "ok", "ticket_id": str(ticket_id), "new_status": status}
