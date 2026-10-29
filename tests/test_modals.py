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


ACTIONS = re.compile(r'<div[^>]*class="modal-actions"[^>]*>(.*?)</div>', re.S)
BUTTON = re.compile(r"<button([^>]*)>([^<]*)</button>")


def _buttons(name):
    """(attrs, label) for each button in a modal's action row, left to right."""
    start = TEMPLATE.index(f'id="{name}"')
    return BUTTON.findall(ACTIONS.search(TEMPLATE, start).group(1))


@pytest.mark.parametrize("name", sorted(RECORD_MODALS))
def test_record_modals_end_cancel_save(name):
    # Copy link alone on the left, then Cancel and the primary Save on the
    # right, as on GNOME, Android and macOS. Never Send, Add or Close.
    labels = [label.strip() for _, label in _buttons(name)]
    assert labels in (["Cancel", "Save"], ["Copy link", "Cancel", "Save"]), labels


def test_every_cancel_answers_escape():
    for name in MODALS:
        for attrs, label in _buttons(name):
            if label.strip() in ("Cancel", "Done"):
                assert "data-cancel" in attrs, f"{name}: {label} needs data-cancel"


def test_primary_button_is_last():
    for name in MODALS:
        buttons = _buttons(name)
        primaries = [i for i, (attrs, _) in enumerate(buttons) if 'class="primary' in attrs]
        assert primaries in ([], [len(buttons) - 1]), name


def test_no_modal_is_sized_by_id():
    for selector in re.findall(r"([^{}]+)\{", STYLE):
        if ".modal" in selector and "#" in selector:
            pytest.fail(f"modal styled by id: {selector.strip()}")
