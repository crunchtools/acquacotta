#!/bin/bash
# Boot gate for container-release.yml: start $IMAGE (the digest that will be
# promoted) the way production does -- systemd as PID 1 -- and require that
# httpd answers / through gunicorn, and that gunicorn has not restarted.
#
# The restart count is the point. On 2026-11-07 an image missing a module
# shipped with the container "healthy" while gunicorn.service boot-looped to a
# restart counter of 139 (RT#1550); a check that only asks "is it up" can
# catch the one moment between restarts and pass.
set -euo pipefail
: "${IMAGE:?IMAGE is the digest under test}"
name="acquacotta-gate-$$"
podman run -d --name "$name" --systemd=always \
    -e FLASK_SECRET_KEY=gate-only -e FLASK_HOST=127.0.0.1 "$IMAGE" >/dev/null
trap 'podman rm -f "$name" >/dev/null' EXIT

for _ in $(seq 1 90); do
    state=$(podman exec "$name" systemctl is-system-running 2>/dev/null || true)
    case "$state" in running|degraded) break ;; esac
    sleep 1
done

code=000
for _ in $(seq 1 60); do
    code=$(podman exec "$name" curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true)
    [ "$code" = 200 ] && break
    sleep 2
done
# Hold long enough for a crashing gunicorn to be restarted (RestartSec=5).
sleep 12
restarts=$(podman exec "$name" systemctl show -p NRestarts --value gunicorn)
active=$(podman exec "$name" systemctl is-active gunicorn httpd | tr '\n' ' ')
echo "GET / -> $code; gunicorn restarts: $restarts; gunicorn/httpd: $active"
if [ "$code" != 200 ] || [ "$restarts" != 0 ] || [ "$active" != "active active " ]; then
    podman exec "$name" journalctl -u gunicorn --no-pager -n 40 || true
    echo "boot gate FAILED" >&2
    exit 1
fi
echo "boot gate passed"
