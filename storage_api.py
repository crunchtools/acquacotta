"""Acquacotta Storage API — dispatch layer for storage backend plugins."""

import plugin_registry


def is_active():
    """Check if a storage backend is active."""
    return plugin_registry.get_active_storage() is not None


def get_pomodoros(ctx, start_date=None, end_date=None):
    backend = plugin_registry.get_active_storage()
    return backend.get_pomodoros(ctx["service"], ctx["location"], start_date, end_date)


def save_pomodoro(ctx, pomodoro):
    backend = plugin_registry.get_active_storage()
    return backend.save_pomodoro(ctx["service"], ctx["location"], pomodoro)


def save_pomodoros_batch(ctx, pomodoros):
    backend = plugin_registry.get_active_storage()
    return backend.save_pomodoros_batch(ctx["service"], ctx["location"], pomodoros)


def update_pomodoro(ctx, pomodoro_id, update_fields):
    backend = plugin_registry.get_active_storage()
    return backend.update_pomodoro(ctx["service"], ctx["location"], pomodoro_id, update_fields)


def delete_pomodoro(ctx, pomodoro_id):
    backend = plugin_registry.get_active_storage()
    return backend.delete_pomodoro(ctx["service"], ctx["location"], pomodoro_id)


def get_settings(ctx, defaults):
    backend = plugin_registry.get_active_storage()
    return backend.get_settings(ctx["service"], ctx["location"], defaults)


def save_settings(ctx, settings_data, replace_all=False):
    backend = plugin_registry.get_active_storage()
    return backend.save_settings(ctx["service"], ctx["location"], settings_data, replace_all=replace_all)


def deduplicate_pomodoros(ctx):
    backend = plugin_registry.get_active_storage()
    return backend.deduplicate_pomodoros(ctx["service"], ctx["location"])


def count_pomodoros(ctx):
    backend = plugin_registry.get_active_storage()
    return backend.count_pomodoros(ctx["service"], ctx["location"])


def clear_pomodoros(ctx):
    backend = plugin_registry.get_active_storage()
    return backend.clear_pomodoros(ctx["service"], ctx["location"])
