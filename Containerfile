FROM quay.io/crunchtools/ubi10-httpd:latest

LABEL maintainer="fatherlinux <scott.mccarty@crunchtools.com>"
LABEL description="Acquacotta recipe tracker — Flask + Gunicorn behind Apache on ubi10-httpd"

# Python 3.12 and pip available in UBI repos — no RHSM needed
RUN dnf install -y python3.12 python3.12-pip && dnf clean all

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3.12 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY sheets_storage.py .
COPY templates/ templates/
COPY static/ static/

# Copy config files and systemd units
COPY rootfs/ /

# Remove default welcome page, enable gunicorn service
RUN rm -f /etc/httpd/conf.d/welcome.conf && \
    chmod +x /usr/local/bin/acquacotta-start.sh && \
    systemctl enable acquacotta

EXPOSE 80
