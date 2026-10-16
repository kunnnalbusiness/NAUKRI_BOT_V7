#!/bin/sh
set -e

# Ensure PLAYWRIGHT_BROWSERS_PATH is set
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"

# If running as root, fix /data and /ms-playwright permissions for pwuser
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/sessions /data/cache /data/config /data/resumes /ms-playwright
    chown -R pwuser:pwuser /data /app /ms-playwright 2>/dev/null || true
    chmod -R 775 /data /ms-playwright 2>/dev/null || true
    exec su -s /bin/sh pwuser -c "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"
else
    mkdir -p /data/sessions /data/cache /data/config /data/resumes 2>/dev/null || true
    exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips='*'
fi
