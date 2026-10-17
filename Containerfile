# Production image for Acquacotta
# Built on top of acquacotta-base - only contains app code
# Very fast to build since infrastructure is pre-cached
#
# Build: podman build -t quay.io/crunchtools/acquacotta .

FROM quay.io/crunchtools/acquacotta-base:latest

WORKDIR /app

# Install new dependencies not in base image
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

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
COPY rt_plugin.py .
COPY settings_plugin.py .
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
RUN python3 -c "import plugin_registry, storage_api, sheets_storage, json_storage_core, json_google_drive_storage, json_pcloud_storage, todos_plugin, discussions_plugin, rt_plugin, pomodoro_tools, mcp_server, mcp_tokens"

# MCP server: a FastMCP process behind Apache. Override the base's Apache conf to
# add the /mcp route, install the mcp systemd unit, and enable it. Layered here
# (not in the base) so it ships without rebuilding the prebuilt base image.
COPY static/acquacotta-http.conf /etc/httpd/conf.d/acquacotta.conf
COPY static/mcp.service /etc/systemd/system/mcp.service
# Refresh gunicorn.service so it forwards the dev/OAuth env vars (and the MCP seal
# key). Shipped here so it lands regardless of the prebuilt base's version.
COPY static/gunicorn.service /etc/systemd/system/gunicorn.service
RUN systemctl enable mcp
