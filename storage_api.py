"""Acquacotta Storage API — dispatch layer for storage backend plugins."""

from googleapiclient.errors import HttpError

import plugin_registry


class StorageUnavailable(HttpError):
    """Raised when no storage backend is active or context is missing."""

    def __init__(self):
        super().__init__(
            resp=type("resp", (), {"status": 503, "reason": "No storage backend active"})(),
            content=b"No storage backend active",
        )


def _require_context(ctx):
    if ctx is None:
        raise StorageUnavailable()


def is_active():
    """Check if a storage backend is active."""
    return plugin_registry.get_active_storage() is not None


def get_pomodoros(ctx, start_date=None, end_date=None):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.get_pomodoros(ctx["service"], ctx["location"], start_date, end_date)


def save_pomodoro(ctx, pomodoro):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.save_pomodoro(ctx["service"], ctx["location"], pomodoro)


def save_pomodoros_batch(ctx, pomodoros):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.save_pomodoros_batch(ctx["service"], ctx["location"], pomodoros)


def update_pomodoro(ctx, pomodoro_id, update_fields):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.update_pomodoro(ctx["service"], ctx["location"], pomodoro_id, update_fields)


def delete_pomodoro(ctx, pomodoro_id):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.delete_pomodoro(ctx["service"], ctx["location"], pomodoro_id)


def get_settings(ctx, defaults):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.get_settings(ctx["service"], ctx["location"], defaults)


def save_settings(ctx, settings_data, replace_all=False):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.save_settings(ctx["service"], ctx["location"], settings_data, replace_all=replace_all)


def deduplicate_pomodoros(ctx):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.deduplicate_pomodoros(ctx["service"], ctx["location"])


def count_pomodoros(ctx):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.count_pomodoros(ctx["service"], ctx["location"])


def clear_pomodoros(ctx):
    _require_context(ctx)
    backend = plugin_registry.get_active_storage()
    return backend.clear_pomodoros(ctx["service"], ctx["location"])
