"""Acquacotta JSON Storage Core — transport-agnostic serialization, CRUD, and filtering.

All functions operate on plain Python dicts/lists. They don't know or care
where the JSON file lives — that's the transport's job.
"""

import json


def parse_pomodoros(json_content):
    """Parse JSON content into a list of pomodoro dicts.

    Returns empty list on None, empty string, or invalid JSON.
    """
    if not json_content:
        return []
    try:
        parsed = json.loads(json_content) if isinstance(json_content, str) else json_content
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, dict):
        return parsed.get("pomodoros", [])
    if isinstance(parsed, list):
        return parsed
    return []


def serialize_pomodoros(pomodoros):
    """Serialize pomodoro list to JSON string."""
    return json.dumps({"pomodoros": pomodoros}, indent=2)


def parse_settings(json_content):
    """Parse JSON content into a settings dict."""
    if not json_content:
        return {}
    try:
        parsed = json.loads(json_content) if isinstance(json_content, str) else json_content
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def serialize_settings(settings):
    """Serialize settings dict to JSON string."""
    return json.dumps(settings, indent=2)


def add_pomodoro(pomodoros, pomodoro):
    """Add a pomodoro if its ID doesn't already exist.

    Returns (updated_list, was_new).
    """
    pomodoro_id = pomodoro.get("id")
    for existing in pomodoros:
        if existing.get("id") == pomodoro_id:
            return pomodoros, False

    pomodoros.append(pomodoro)
    return pomodoros, True


def add_pomodoros_batch(pomodoros, new_pomodoros):
    """Add multiple pomodoros, skipping duplicates.

    Returns (updated_list, count_added).
    """
    existing_ids = {p.get("id") for p in pomodoros}
    added = 0
    for p in new_pomodoros:
        if p.get("id") not in existing_ids:
            pomodoros.append(p)
            existing_ids.add(p.get("id"))
            added += 1
    return pomodoros, added


def update_pomodoro(pomodoros, pomodoro_id, update_fields):
    """Update a pomodoro by ID.

    Returns (updated_list, was_found).
    """
    for p in pomodoros:
        if p.get("id") == pomodoro_id:
            for key, value in update_fields.items():
                p[key] = value
            return pomodoros, True
    return pomodoros, False


def delete_pomodoro(pomodoros, pomodoro_id):
    """Delete a pomodoro by ID.

    Returns (updated_list, was_found).
    """
    original_len = len(pomodoros)
    pomodoros = [p for p in pomodoros if p.get("id") != pomodoro_id]
    return pomodoros, len(pomodoros) < original_len


def filter_by_date(pomodoros, start_date=None, end_date=None):
    """Filter pomodoros by date range and sort descending by start_time."""
    filtered = pomodoros
    if start_date:
        filtered = [p for p in filtered if p.get("start_time", "") >= start_date]
    if end_date:
        filtered = [p for p in filtered if p.get("start_time", "") <= end_date]
    filtered.sort(key=lambda p: p.get("start_time", ""), reverse=True)
    return filtered


def deduplicate(pomodoros):
    """Remove duplicate pomodoros (keeps first occurrence of each ID).

    Returns (deduped_list, count_removed).
    """
    seen = set()
    deduped = []
    for p in pomodoros:
        pid = p.get("id")
        if pid not in seen:
            seen.add(pid)
            deduped.append(p)
    removed = len(pomodoros) - len(deduped)
    return deduped, removed


def merge_settings(existing, updates, replace_all=False):
    """Merge settings updates into existing settings.

    If replace_all is True, return updates as the new settings.
    Otherwise, overlay updates onto existing.
    """
    if replace_all:
        return dict(updates)
    merged = dict(existing)
    merged.update(updates)
    return merged
