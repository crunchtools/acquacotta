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
COPY todos_plugin.py .
COPY transports/ transports/
COPY templates/ templates/
COPY static/ static/
