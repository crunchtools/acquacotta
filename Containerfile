# Production image for Acquacotta
# Built on top of acquacotta-base - only contains app code
# Very fast to build since infrastructure is pre-cached
#
# Build: podman build -t quay.io/crunchtools/acquacotta .

FROM quay.io/crunchtools/acquacotta-base:latest

WORKDIR /app

# Copy only application code (fast)
COPY app.py .
COPY plugin_registry.py .
COPY storage_api.py .
COPY sheets_storage.py .
COPY templates/ templates/
COPY static/ static/
