# ==============================================================================
# STAGE 1: Build React Frontend Single Page App (SPA)
# ==============================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ==============================================================================
# STAGE 2: Playwright Python Production Image (Pinned to 1.50.0)
# ==============================================================================
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=8000 \
    DATA_DIR=/data \
    HEADLESS=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install tini (zombie process reaper), xvfb, and required fonts/system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    xvfb \
    fonts-liberation \
    fonts-noto-color-emoji \
    fontconfig \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create persistent data directories and ensure pwuser owns browser path & data
RUN mkdir -p /data/sessions /data/cache /data/config /data/resumes /ms-playwright \
    && chown -R pwuser:pwuser /data /app /ms-playwright \
    && chmod -R 775 /data /ms-playwright

# Install pinned Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and common Python source with pwuser ownership
COPY --chown=pwuser:pwuser backend/ ./backend/
COPY --chown=pwuser:pwuser common/ ./common/
COPY --chown=pwuser:pwuser *.py ./

# Copy built frontend SPA assets from Stage 1 into /app/frontend/dist
COPY --from=frontend-builder --chown=pwuser:pwuser /app/frontend/dist ./frontend/dist

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Healthcheck probe for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:' + str(__import__('os').environ.get('PORT', 8000)) + '/healthz').getcode() == 200 else 1)"

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
