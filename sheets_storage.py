"""Google Sheets storage backend for Acquacotta (gspread)."""

import json

import gspread

PLUGIN_METADATA = {
    "id": "sheets",
    "name": "Google Sheets",
    "description": "Store data in your Google Sheets spreadsheet",
    "version": "2.0.0",
    "type": "storage",
    "author": "crunchtools",
    "frontend_fields": ["spreadsheet_id"],
    "auth_flow": "google_oauth",
}

POMODORO_MIN_COLUMNS = 6  # id, name, type, start_time, end_time, duration_minutes
POMODORO_TOTAL_COLUMNS = 7  # includes optional notes column
SETTINGS_MIN_COLUMNS = 2  # key, value


def build_context(credentials, request_creds):
    """Build Sheets-specific storage context from credentials."""
    gc = gspread.authorize(credentials)
    return {
        "service": gc,
        "location": request_creds.get("spreadsheet_id"),
    }


def get_pomodoros(gc, spreadsheet_id, start_date=None, end_date=None):
    """Get pomodoros from Google Sheets."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    rows = ws.get("A2:G")

    pomodoros = []
    for row in rows:
        if len(row) < POMODORO_MIN_COLUMNS:
            continue
        pomo = {
            "id": row[0],
            "name": row[1],
            "type": row[2],
            "start_time": row[3],
            "end_time": row[4],
            "duration_minutes": int(row[5]),
            "notes": row[6] if len(row) > POMODORO_MIN_COLUMNS else None,
        }

        if start_date and pomo["start_time"] < start_date:
            continue
        if end_date and pomo["start_time"] > end_date:
            continue

        pomodoros.append(pomo)

    pomodoros.sort(key=lambda p: p["start_time"], reverse=True)
    return pomodoros


def save_pomodoro(gc, spreadsheet_id, pomodoro):
    """Save a new pomodoro to Google Sheets (with duplicate check)."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    existing_ids = ws.col_values(1)

    if pomodoro["id"] in existing_ids:
        return False

    ws.append_row(
        [
            pomodoro["id"],
            pomodoro["name"],
            pomodoro["type"],
            pomodoro["start_time"],
            pomodoro["end_time"],
            pomodoro["duration_minutes"],
            pomodoro.get("notes") or "",
        ],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
    )
    return True


def save_pomodoros_batch(gc, spreadsheet_id, pomodoros):
    """Save multiple pomodoros to Google Sheets in a single request (with duplicate check)."""
    if not pomodoros:
        return 0

    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    existing_ids = set(ws.col_values(1))

    rows = []
    for p in pomodoros:
        if p["id"] not in existing_ids:
            rows.append(
                [
                    p["id"],
                    p["name"],
                    p["type"],
                    p["start_time"],
                    p["end_time"],
                    p["duration_minutes"],
                    p.get("notes") or "",
                ]
            )

    if not rows:
        return 0

    ws.append_rows(rows, value_input_option="RAW", insert_data_option="INSERT_ROWS")
    return len(rows)


def update_pomodoro(gc, spreadsheet_id, pomodoro_id, update_fields):
    """Update a pomodoro in Google Sheets."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    id_col = ws.col_values(1)

    row_index = None
    for i, cell_val in enumerate(id_col):
        if cell_val == pomodoro_id:
            row_index = i + 1  # 1-indexed
            break

    if row_index is None:
        return False

    current_values = ws.row_values(row_index)
    while len(current_values) < POMODORO_TOTAL_COLUMNS:
        current_values.append("")

    current_values[1] = update_fields.get("name", current_values[1])
    current_values[2] = update_fields.get("type", current_values[2])
    current_values[3] = update_fields.get("start_time", current_values[3])
    current_values[4] = update_fields.get("end_time", current_values[4])
    current_values[5] = update_fields.get("duration_minutes", current_values[5])
    current_values[6] = update_fields.get("notes") or ""

    ws.update(range_name=f"A{row_index}:G{row_index}", values=[current_values])
    return True


def delete_pomodoro(gc, spreadsheet_id, pomodoro_id):
    """Delete a pomodoro from Google Sheets."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    id_col = ws.col_values(1)

    row_index = None
    for i, cell_val in enumerate(id_col):
        if cell_val == pomodoro_id:
            row_index = i + 1  # 1-indexed
            break

    if row_index is None:
        return False

    ws.delete_rows(row_index)
    return True


def get_settings(gc, spreadsheet_id, defaults):
    """Get settings from Google Sheets."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Settings")
    rows = ws.get("A2:B")

    settings = dict(defaults)
    for row in rows:
        if len(row) >= SETTINGS_MIN_COLUMNS:
            key = row[0]
            try:
                value = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                value = row[1]
            settings[key] = value

    return settings


def deduplicate_pomodoros(gc, spreadsheet_id):
    """Remove duplicate pomodoros from Google Sheets (keeps first occurrence of each ID).

    Returns:
        dict: {'removed': count_removed, 'total': total_rows}
    """
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    id_col = ws.col_values(1)

    seen_ids = set()
    rows_to_delete = []

    for i, cell_val in enumerate(id_col):
        if i == 0:
            continue
        if cell_val:
            if cell_val in seen_ids:
                rows_to_delete.append(i + 1)  # 1-indexed
            else:
                seen_ids.add(cell_val)

    if not rows_to_delete:
        return {"removed": 0, "total": len(id_col) - 1}

    # Delete in reverse order so indices don't shift
    for row_index in reversed(rows_to_delete):
        ws.delete_rows(row_index)

    return {"removed": len(rows_to_delete), "total": len(id_col) - 1 - len(rows_to_delete)}


def save_settings(gc, spreadsheet_id, settings_data, replace_all=False):
    """Save settings to Google Sheets."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Settings")

    if replace_all:
        ws.batch_clear(["A2:B"])

        rows = []
        for key, value in settings_data.items():
            rows.append([key, json.dumps(value)])

        if rows:
            ws.update(range_name="A2:B", values=rows)
        return

    # Incremental update mode (default)
    existing_rows = ws.get("A2:B")
    existing_keys = {}
    for i, row in enumerate(existing_rows):
        if row:
            existing_keys[row[0]] = i + 2  # 1-indexed, +1 for header

    updates = []
    appends = []

    for key, value in settings_data.items():
        value_str = json.dumps(value)
        if key in existing_keys:
            row_index = existing_keys[key]
            updates.append({"range": f"A{row_index}:B{row_index}", "values": [[key, value_str]]})
        else:
            appends.append([key, value_str])

    if updates:
        ws.batch_update(updates)

    if appends:
        ws.append_rows(appends, value_input_option="RAW", insert_data_option="INSERT_ROWS")


def count_pomodoros(gc, spreadsheet_id):
    """Count pomodoros efficiently by fetching only the ID column."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    id_col = ws.col_values(1)
    return max(0, len(id_col) - 1)


def clear_pomodoros(gc, spreadsheet_id):
    """Clear all pomodoro data rows (keeps headers)."""
    ws = gc.open_by_key(spreadsheet_id).worksheet("Pomodoros")
    id_col = ws.col_values(1)
    row_count = len(id_col)

    if row_count <= 1:
        return {"status": "ok", "cleared": 0}

    ws.delete_rows(2, row_count)
    return {"status": "ok", "cleared": row_count - 1}
