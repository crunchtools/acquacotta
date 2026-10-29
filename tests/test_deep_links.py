"""Deep links handed out by MCP tools (deep_links.py)."""

import pytest

import deep_links


@pytest.fixture
def public_url(monkeypatch):
    monkeypatch.setenv(deep_links.PUBLIC_URL_ENV, "https://acq.example.com/")


def test_item_link(public_url):
    assert deep_links.app_link("rt", "ticket", 1529) == "https://acq.example.com/#rt/ticket/1529"


def test_segments_are_encoded_and_trailing_blanks_dropped(public_url):
    assert deep_links.app_link("discussions", "person", "Jane Doe/Ops") == (
        "https://acq.example.com/#discussions/person/Jane%20Doe%2FOps"
    )
    assert deep_links.app_link("todos") == "https://acq.example.com/#todos"


def test_unset_means_no_link(monkeypatch):
    monkeypatch.delenv(deep_links.PUBLIC_URL_ENV, raising=False)
    monkeypatch.setenv("OAUTH_REDIRECT_BASE", "http://localhost:5000")
    assert deep_links.app_link("todos", "item", "a") == ""


@pytest.mark.parametrize("value", ["", "acq.example.com", "javascript:alert(1)"])
def test_no_usable_base_means_no_link(monkeypatch, value):
    monkeypatch.setenv(deep_links.PUBLIC_URL_ENV, value)
    assert deep_links.app_link("todos", "item", "a") == ""
    assert deep_links.with_link({"id": "a"}, "todos", "item") == {"id": "a"}


def test_with_link(public_url):
    assert deep_links.with_link({"id": "t1", "title": "x"}, "todos", "item") == {
        "id": "t1",
        "title": "x",
        "link": "https://acq.example.com/#todos/item/t1",
    }
    assert deep_links.with_link(None, "rt", "ticket") is None
    assert deep_links.with_link({"title": "no id"}, "todos", "item") == {"title": "no id"}
    assert [t["link"] for t in deep_links.with_links([{"id": "1"}, {"id": "2"}], "rt", "ticket")] == [
        "https://acq.example.com/#rt/ticket/1",
        "https://acq.example.com/#rt/ticket/2",
    ]
