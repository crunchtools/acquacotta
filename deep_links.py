"""Deep links into the Acquacotta web app, for records handed out over MCP.

The web app routes on the URL hash (``/#todos/item/<id>``, ``/#rt/ticket/<id>``;
see ``parseRoute`` in static/js/utils.js), so an agent can give the user a link
that opens the exact item. The server only learns its public URL from the
environment: ``ACQUACOTTA_PUBLIC_URL``, else ``OAUTH_REDIRECT_BASE``. With
neither set, records carry no link.
"""

import os
from urllib.parse import quote

PUBLIC_URL_ENV = "ACQUACOTTA_PUBLIC_URL"


def app_link(view, kind="", item_id=""):
    """The deep link for a view, sub-view or item, or "" without a public URL."""
    base = (os.environ.get(PUBLIC_URL_ENV) or os.environ.get("OAUTH_REDIRECT_BASE") or "").strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        return ""
    parts = [str(p) for p in (view, kind, item_id)]
    while len(parts) > 1 and not parts[-1]:
        parts.pop()
    return f"{base}/#" + "/".join(quote(p, safe="") for p in parts)


def with_link(record, view, kind):
    """``record`` plus ``link`` to the item its ``id`` names; other values pass through."""
    if not isinstance(record, dict) or not record.get("id"):
        return record
    link = app_link(view, kind, record["id"])
    return {**record, "link": link} if link else record


def with_links(records, view, kind):
    """``with_link`` over a list of records."""
    return [with_link(r, view, kind) for r in records] if isinstance(records, list) else records
