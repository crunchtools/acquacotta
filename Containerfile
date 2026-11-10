# Production image for Acquacotta
# Built on top of acquacotta-base - only contains app code
# Very fast to build since infrastructure is pre-cached
#
# Build: podman build -t quay.io/crunchtools/acquacotta .

# RT#1564: same lock stage as Containerfile.base. This file also pip-installs
# from a requirements export (to pick up deps added since the base image was
# last rebuilt), so it needs the same uv.lock -> requirements.txt conversion.
FROM quay.io/hummingbird/python:3.14-builder AS lock
USER 0
RUN pip install --no-cache-dir uv==0.13.7
WORKDIR /lock
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --python 3.12 \
      --format requirements-txt -o /requirements.txt

FROM quay.io/crunchtools/acquacotta-base:latest

WORKDIR /app

# Install new dependencies not in base image. Dependencies come from uv.lock,
# not a separately-compiled requirements.txt (RT#1564).
COPY --from=lock /requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --no-deps -r /tmp/requirements.txt

# Copy only application code (fast)
COPY app.py .
COPY plugin_registry.py .
COPY storage_api.py .
COPY sheets_storage.py .
COPY json_storage_core.py .
COPY json_google_drive_storage.py .
COPY json_pcloud_storage.py .
COPY todos_plugin.py .
COPY discussions_plugin.py .
COPY plugin_common.py .
COPY deep_links.py .
COPY rt_plugin.py .
COPY social_plugin.py .
COPY settings_plugin.py .
COPY timer_sync_plugin.py .
COPY assistant_plugin.py .
COPY checklists_plugin.py .
COPY pomodoro_tools.py .
COPY mcp_server.py .
COPY mcp_tokens.py .
COPY transports/ transports/
COPY templates/ templates/
COPY static/ static/

# Fail the build if any app module is missing from the image (e.g. a new top-level
# module was added but not COPYed above — which ships a container that crashes on
# boot with ModuleNotFoundError). app.py needs runtime env to import, so import the
# plugin/storage modules it pulls in instead.
RUN python3 -c "import plugin_registry, storage_api, sheets_storage, json_storage_core, json_google_drive_storage, json_pcloud_storage, todos_plugin, discussions_plugin, plugin_common, deep_links, rt_plugin, social_plugin, settings_plugin, timer_sync_plugin, assistant_plugin, checklists_plugin, pomodoro_tools, mcp_server, mcp_tokens"

# MCP server: a FastMCP process behind Apache. Override the base's Apache conf to
# add the /mcp route, install the mcp systemd unit, and enable it. Layered here
# (not in the base) so it ships without rebuilding the prebuilt base image.
COPY static/acquacotta-http.conf /etc/httpd/conf.d/acquacotta.conf
COPY static/mcp.service /etc/systemd/system/mcp.service
# Refresh gunicorn.service so it forwards the dev/OAuth env vars (and the MCP seal
# key). Shipped here so it lands regardless of the prebuilt base's version.
COPY static/gunicorn.service /etc/systemd/system/gunicorn.service
RUN systemctl enable mcp
