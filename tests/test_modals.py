"""Every modal in every view and plugin uses the shared modal component.

Sizes come from the .modal class (record modals) or .modal-compact
(confirmations and system prompts), never from a per-modal rule, so
to-dos, discussions, tickets and pomodoros look and size the same.
"""

import re
from pathlib import Path

import pytest

TEMPLATE = (Path(__file__).parent.parent / "templates" / "index.html").read_text()
STYLE = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", TEMPLATE, re.S))

OVERLAY = re.compile(r'<div[^>]*class="modal-overlay"[^>]*>\s*<div([^>]*)>', re.S)
OVERLAY_ID = re.compile(
    r'<div[^>]*id="([^"]+)"[^>]*class="modal-overlay"|<div[^>]*class="modal-overlay"[^>]*id="([^"]+)"'
)

# Record modals: viewing or editing one item. These must be the full-size default.
RECORD_MODALS = {"edit-modal", "add-modal", "todo-edit-modal", "discussion-edit-modal", "rt-detail-modal"}


MODALS = {
    (ident.group(1) or ident.group(2)): m.group(1)
    for m in OVERLAY.finditer(TEMPLATE)
    if (ident := OVERLAY_ID.match(TEMPLATE, m.start()))
}


def test_every_overlay_wraps_a_modal():
    assert RECORD_MODALS <= set(MODALS)
    for name, attrs in MODALS.items():
        classes = re.search(r'class="([^"]*)"', attrs).group(1).split()
        assert "modal" in classes, name
        assert set(classes) <= {"modal", "modal-compact"}, name
        assert "style=" not in attrs, f"{name}: size modals with classes, not inline style"


@pytest.mark.parametrize("name", sorted(RECORD_MODALS))
def test_record_modals_are_full_size(name):
    assert "modal-compact" not in MODALS[name]


def test_no_modal_is_sized_by_id():
    for selector in re.findall(r"([^{}]+)\{", STYLE):
        if ".modal" in selector and "#" in selector:
            pytest.fail(f"modal styled by id: {selector.strip()}")
