"""Acquacotta Storage API — dispatch layer for storage backend plugins.

Every operation dispatches to the backend carried in the request context
(`ctx["backend"]`), which the caller resolves per-user. The active backend is
never read from a process-global here, so one user's choice can never route
another user's data to the wrong backend.
"""

import plugin_registry


class StorageUnavailable(Exception):
    """Raised when no storage backend is active or context is missing."""


def _backend(ctx):
    """Return the per-user backend from the context, or raise if absent."""
    if ctx is None:
        raise StorageUnavailable()
    backend = ctx.get("backend")
    if backend is None:
        raise StorageUnavailable()
    return backend


def is_active():
    """Check if a storage backend is registered (registration-level check)."""
    return plugin_registry.get_active_storage() is not None


def get_pomodoros(ctx, start_date=None, end_date=None):
    backend = _backend(ctx)
    return backend.get_pomodoros(ctx["service"], ctx["location"], start_date, end_date)


def save_pomodoro(ctx, pomodoro):
    backend = _backend(ctx)
    return backend.save_pomodoro(ctx["service"], ctx["location"], pomodoro)


def save_pomodoros_batch(ctx, pomodoros):
    backend = _backend(ctx)
    return backend.save_pomodoros_batch(ctx["service"], ctx["location"], pomodoros)


def update_pomodoro(ctx, pomodoro_id, update_fields):
    backend = _backend(ctx)
    return backend.update_pomodoro(ctx["service"], ctx["location"], pomodoro_id, update_fields)


def delete_pomodoro(ctx, pomodoro_id):
    backend = _backend(ctx)
    return backend.delete_pomodoro(ctx["service"], ctx["location"], pomodoro_id)


def get_settings(ctx, defaults):
    backend = _backend(ctx)
    return backend.get_settings(ctx["service"], ctx["location"], defaults)


def save_settings(ctx, settings_data, replace_all=False):
    backend = _backend(ctx)
    return backend.save_settings(ctx["service"], ctx["location"], settings_data, replace_all=replace_all)


def deduplicate_pomodoros(ctx):
    backend = _backend(ctx)
    return backend.deduplicate_pomodoros(ctx["service"], ctx["location"])


def count_pomodoros(ctx):
    backend = _backend(ctx)
    return backend.count_pomodoros(ctx["service"], ctx["location"])


def clear_pomodoros(ctx):
    backend = _backend(ctx)
    return backend.clear_pomodoros(ctx["service"], ctx["location"])
