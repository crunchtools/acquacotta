"""Google Sheets storage backend for Acquacotta."""

import json

# Column counts for Sheets data validation
POMODORO_MIN_COLUMNS = 6  # id, name, type, start_time, end_time, duration_minutes
POMODORO_TOTAL_COLUMNS = 7  # includes optional notes column
SETTINGS_MIN_COLUMNS = 2  # key, value


def get_pomodoros(sheets_service, spreadsheet_id, start_date=None, end_date=None):
    """Get pomodoros from Google Sheets."""
    sheets_response = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A2:G",
        )
        .execute()
    )

    rows = sheets_response.get("values", [])
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

        # Filter by date if specified
        if start_date and pomo["start_time"] < start_date:
            continue
        if end_date and pomo["start_time"] > end_date:
            continue

        pomodoros.append(pomo)

    # Sort by start_time descending
    pomodoros.sort(key=lambda p: p["start_time"], reverse=True)
    return pomodoros


def save_pomodoro(sheets_service, spreadsheet_id, pomodoro):
    """Save a new pomodoro to Google Sheets (with duplicate check)."""
    # First check if this ID already exists to prevent duplicates
    id_lookup = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A:A",
        )
        .execute()
    )

    existing_ids = id_lookup.get("values", [])
    pomodoro_id = pomodoro["id"]

    for row in existing_ids:
        if row and row[0] == pomodoro_id:
            # ID already exists, skip insert (could also update here)
            return False

    # ID doesn't exist, append new row
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Pomodoros!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [
                [
                    pomodoro_id,
                    pomodoro["name"],
                    pomodoro["type"],
                    pomodoro["start_time"],
                    pomodoro["end_time"],
                    pomodoro["duration_minutes"],
                    pomodoro.get("notes") or "",
                ]
            ]
        },
    ).execute()
    return True


def save_pomodoros_batch(sheets_service, spreadsheet_id, pomodoros):
    """Save multiple pomodoros to Google Sheets in a single request (with duplicate check)."""
    if not pomodoros:
        return 0

    # First get all existing IDs
    id_lookup = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A:A",
        )
        .execute()
    )

    existing_ids = set()
    for row in id_lookup.get("values", []):
        if row:
            existing_ids.add(row[0])

    # Filter out pomodoros that already exist
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

    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Pomodoros!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def update_pomodoro(sheets_service, spreadsheet_id, pomodoro_id, update_fields):
    """Update a pomodoro in Google Sheets."""
    # Find the row with this ID
    id_lookup = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A:A",
        )
        .execute()
    )

    rows = id_lookup.get("values", [])
    row_index = None
    for i, row in enumerate(rows):
        if row and row[0] == pomodoro_id:
            row_index = i + 1  # 1-indexed
            break

    if row_index is None:
        return False

    # Get current row data
    current_row = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"Pomodoros!A{row_index}:G{row_index}",
        )
        .execute()
    )

    current_values = current_row.get("values", [[]])[0]
    while len(current_values) < POMODORO_TOTAL_COLUMNS:
        current_values.append("")

    # Update fields
    current_values[1] = update_fields.get("name", current_values[1])
    current_values[2] = update_fields.get("type", current_values[2])
    current_values[3] = update_fields.get("start_time", current_values[3])
    current_values[4] = update_fields.get("end_time", current_values[4])
    current_values[5] = update_fields.get("duration_minutes", current_values[5])
    current_values[6] = update_fields.get("notes") or ""

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Pomodoros!A{row_index}:G{row_index}",
        valueInputOption="RAW",
        body={"values": [current_values]},
    ).execute()

    return True


def delete_pomodoro(sheets_service, spreadsheet_id, pomodoro_id):
    """Delete a pomodoro from Google Sheets."""
    # Find the row with this ID
    id_lookup = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A:A",
        )
        .execute()
    )

    rows = id_lookup.get("values", [])
    row_index = None
    for i, row in enumerate(rows):
        if row and row[0] == pomodoro_id:
            row_index = i  # 0-indexed for delete
            break

    if row_index is None:
        return False

    # Get sheet ID
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_id = None
    for sheet in spreadsheet["sheets"]:
        if sheet["properties"]["title"] == "Pomodoros":
            sheet_id = sheet["properties"]["sheetId"]
            break

    if sheet_id is None:
        return False

    # Delete the row
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_index,
                            "endIndex": row_index + 1,
                        }
                    }
                }
            ]
        },
    ).execute()

    return True


def get_settings(sheets_service, spreadsheet_id, defaults):
    """Get settings from Google Sheets."""
    sheets_response = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Settings!A2:B",
        )
        .execute()
    )

    rows = sheets_response.get("values", [])
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


def deduplicate_pomodoros(sheets_service, spreadsheet_id):
    """Remove duplicate pomodoros from Google Sheets (keeps first occurrence of each ID).

    Returns:
        dict: {'removed': count_removed, 'total': total_rows}
    """
    # Get all pomodoros with their row indices
    id_lookup = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Pomodoros!A:A",
        )
        .execute()
    )

    rows = id_lookup.get("values", [])

    # Track seen IDs and rows to delete (0-indexed)
    seen_ids = set()
    rows_to_delete = []

    for i, row in enumerate(rows):
        if i == 0:
            # Skip header row
            continue
        if row:
            pomodoro_id = row[0]
            if pomodoro_id in seen_ids:
                rows_to_delete.append(i)
            else:
                seen_ids.add(pomodoro_id)

    if not rows_to_delete:
        return {"removed": 0, "total": len(rows) - 1}  # -1 for header

    # Get sheet ID
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    sheet_id = None
    for sheet in spreadsheet["sheets"]:
        if sheet["properties"]["title"] == "Pomodoros":
            sheet_id = sheet["properties"]["sheetId"]
            break

    if sheet_id is None:
        return {"removed": 0, "total": len(rows) - 1, "error": "Pomodoros sheet not found"}

    # Delete rows in reverse order (so indices don't shift)
    rows_to_delete.reverse()

    requests = []
    for row_index in rows_to_delete:
        requests.append(
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_index,
                        "endIndex": row_index + 1,
                    }
                }
            }
        )

    # Execute batch delete
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()

    return {"removed": len(rows_to_delete), "total": len(rows) - 1 - len(rows_to_delete)}


def save_settings(sheets_service, spreadsheet_id, settings_data, replace_all=False):
    """Save settings to Google Sheets.

    Args:
        sheets_service: Google Sheets API service
        spreadsheet_id: ID of the spreadsheet
        settings_data: Dictionary of settings to save
        replace_all: If True, clear all settings first and replace with new data
    """
    if replace_all:
        # Clear all settings rows (keep header) and replace with new data
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="Settings!A2:B",
        ).execute()

        # Prepare all settings as rows
        rows = []
        for key, value in settings_data.items():
            value_str = json.dumps(value)
            rows.append([key, value_str])

        # Write all settings at once
        if rows:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Settings!A2:B",
                valueInputOption="RAW",
                body={"values": rows},
            ).execute()
        return

    # Incremental update mode (default)
    # Get existing settings
    existing_settings = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Settings!A2:B",
        )
        .execute()
    )

    existing_rows = existing_settings.get("values", [])
    existing_keys = {row[0]: i + 2 for i, row in enumerate(existing_rows) if row}  # 1-indexed, +1 for header

    # Prepare updates and appends
    updates = []
    appends = []

    for key, value in settings_data.items():
        value_str = json.dumps(value)
        if key in existing_keys:
            row_index = existing_keys[key]
            updates.append(
                {
                    "range": f"Settings!A{row_index}:B{row_index}",
                    "values": [[key, value_str]],
                }
            )
        else:
            appends.append([key, value_str])

    # Batch update existing
    if updates:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": updates,
            },
        ).execute()

    # Append new settings
    if appends:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Settings!A:B",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": appends},
        ).execute()
