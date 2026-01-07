ARG BUILD_FROM=ghcr.io/hassio-addons/debian-base:7.3.3
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies required for Playwright and Chromium
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        curl \
        nodejs \
        npm \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        xvfb \
        x11vnc \
        fluxbox \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# Set environment variables for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app
    
# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Install Playwright and its browsers
# Debian-based image supports Playwright on ARM64
RUN pip3 install --no-cache-dir --break-system-packages playwright && \
    playwright install --with-deps chromium

# Verify playwright is importable
RUN python3 -c "from playwright.async_api import async_playwright; print('Playwright imported successfully')"

# Copy application files
COPY app/ /app/
COPY rootfs /

# Make scripts executable
RUN chmod a+x /usr/local/bin/run.sh

# Create share directory
RUN mkdir -p /share/amazonparent && \
    chmod 700 /share/amazonparent

# Expose ports
EXPOSE 8100 5903

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8100/api/health || exit 1

# Labels
LABEL \
    io.hass.name="Amazon Parent Dashboard Auth" \
    io.hass.description="Authentication service for Amazon Parent Dashboard" \
    io.hass.type="addon" \
    io.hass.version="0.1.4"
