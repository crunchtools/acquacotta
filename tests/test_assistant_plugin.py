"""Tests for assistant_plugin: registry-driven context and the Gemini text call."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import assistant_plugin
import plugin_registry
import pomodoro_tools
import social_plugin
import todos_plugin

CONFIG = {"gemini_api_key": "gm-key", "gemini_model": "gemini-test"}


@pytest.fixture
def registry(monkeypatch):
    """An isolated registry: an active plugin with context, one without a hook, one inactive."""
    monkeypatch.setattr(plugin_registry, "_plugins", {})
    good = SimpleNamespace(assistant_context=lambda _s, _f: {"minutes": 25})
    for pid, module in (("good", good), ("plain", SimpleNamespace()), ("off", good)):
        plugin_registry.register("extension", pid, module, {"id": pid, "type": "extension"})
        if pid != "off":
            plugin_registry.activate_extension(pid)


class TestContext:
    def test_only_active_plugins_with_a_hook(self, registry):
        assert assistant_plugin.gather_context(None, "f") == {"good": {"minutes": 25}}

    def test_per_user_disabled_plugin_is_left_out(self, registry):
        assert assistant_plugin.gather_context(None, "f", enabled=lambda pid: pid != "good") == {}

    @pytest.mark.parametrize("question", [None, "  ", 5, "x" * 2001])
    def test_bad_question_rejected(self, question):
        with pytest.raises(ValueError):
            assistant_plugin.build_prompt(question, {})

    def test_context_is_capped(self):
        prompt = assistant_plugin.build_prompt("hi", {"a": "x" * 100000})
        assert len(prompt) < assistant_plugin.MAX_CONTEXT_CHARS + 200


class TestChat:
    def test_plain_text_call_through_social_gemini(self, monkeypatch):
        calls = []

        class Resp:
            status_code = 200

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": " You did 25 minutes. "}]}}]}

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return Resp()

        monkeypatch.setattr(social_plugin.requests, "post", fake_post)
        answer = assistant_plugin.chat(CONFIG, "How long?", {"pomodoro": {"minutes": 25}})
        assert answer == "You did 25 minutes."
        url, kwargs = calls[0]
        assert url == f"{social_plugin.GEMINI_API_BASE}/gemini-test:generateContent"
        assert kwargs["json"]["generationConfig"] == {"responseMimeType": "text/plain"}
        assert "QUESTION:\nHow long?" in kwargs["json"]["contents"][0]["parts"][0]["text"]
        assert "productivity dashboard" in kwargs["json"]["systemInstruction"]["parts"][0]["text"]

    def test_unreadable_answer(self):
        with pytest.raises(social_plugin.SocialError):
            assistant_plugin.extract_answer({"candidates": []})

    def test_missing_key(self):
        with pytest.raises(ValueError):
            assistant_plugin.chat({}, "hi", {})


class TestPomodoroContextHook:
    def test_one_read_split_into_7_and_30_day_summaries(self, monkeypatch):
        fixed_now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        reads = []
        records = [
            {"type": "Product", "duration_minutes": 25, "start_time": "2026-07-30T09:00:00Z"},
            {"type": "Content", "duration_minutes": 50, "start_time": "2026-07-10T09:00:00Z"},
        ]

        def fake_get(_d, _f, start_date=None, end_date=None):
            reads.append((start_date, end_date))
            return list(records)

        monkeypatch.setattr(pomodoro_tools, "datetime", FixedClock)
        monkeypatch.setattr(pomodoro_tools.drive_storage, "get_pomodoros", fake_get)
        context = pomodoro_tools.assistant_context(None, "f")
        assert reads == [("2026-07-01T12:00:00Z", "2026-07-31T12:00:00Z")]
        assert context["last_7_days"] == {
            "total_minutes": 25,
            "total_count": 1,
            "by_category": {"Product": {"minutes": 25, "count": 1}},
        }
        assert context["last_30_days"]["total_minutes"] == 75
        assert context["last_30_days"]["total_count"] == 2


class TestTodosContextHook:
    def test_pending_only_capped_and_projected(self, monkeypatch):
        calls = []
        todos = [
            {"title": f"t{i}", "priority": "high", "due_date": "2026-08-01", "notes": "private", "status": "pending"}
            for i in range(60)
        ]

        def fake_query(_d, _f, status=None, **_kw):
            calls.append(status)
            return list(todos)

        monkeypatch.setattr(todos_plugin, "query_todos", fake_query)
        context = todos_plugin.assistant_context(None, "f")
        assert calls == ["pending"]
        assert len(context) == 50
        assert context[0] == {"title": "t0", "priority": "high", "due_date": "2026-08-01"}
