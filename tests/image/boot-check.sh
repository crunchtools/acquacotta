#!/bin/bash
# Boot gate, run INSIDE the image with systemd as PID 1 (the `app-boot` check in
# pyproject.toml's [tool.sdlc.ci]): require that httpd answers / through
# gunicorn, and that gunicorn has not restarted.
#
# The restart count is the point. On 2026-11-07 an image missing a module
# shipped with the container "healthy" while gunicorn.service boot-looped to a
# restart counter of 139 (RT#1550); a check that only asks "is it up" can
# catch the one moment between restarts and pass.
set -euo pipefail

# The gate cannot pass -e to the container, so the units get production's one
# required variable from the manager, then start afresh: stop, flush the
# failures and restart count left by booting without it, start.
systemctl set-environment FLASK_SECRET_KEY=gate-only FLASK_HOST=127.0.0.1
systemctl stop gunicorn mcp
systemctl reset-failed
systemctl start gunicorn mcp

code=000
for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true)
    [ "$code" = 200 ] && break
    sleep 2
done
# Hold long enough for a crashing gunicorn to be restarted (RestartSec=5).
sleep 12
restarts=$(systemctl show -p NRestarts --value gunicorn)
active=$(systemctl is-active gunicorn httpd | tr '\n' ' ' || true)
echo "GET / -> $code; gunicorn restarts: $restarts; gunicorn/httpd: $active"
if [ "$code" != 200 ] || [ "$restarts" != 0 ] || [ "$active" != "active active " ]; then
    journalctl -u gunicorn --no-pager -n 40 || true
    echo "boot gate FAILED" >&2
    exit 1
fi
echo "boot gate passed"
