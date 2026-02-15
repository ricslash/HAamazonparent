#!/bin/bash
# ==============================================================================
# Standalone entrypoint for Amazon Parent Dashboard Auth Service
# (Does not require bashio/HA Supervisor)
# ==============================================================================
set -e

echo "[INFO] Starting Amazon Parent Dashboard Auth Service (standalone)..."

# Use environment variables directly (no bashio)
export LOG_LEVEL="${LOG_LEVEL:-info}"
export AUTH_TIMEOUT="${AUTH_TIMEOUT:-300}"
export SESSION_DURATION="${SESSION_DURATION:-86400}"
export KEEPALIVE_INTERVAL="${KEEPALIVE_INTERVAL:-2700}"
export AMAZON_EMAIL="${AMAZON_EMAIL:-}"
export AMAZON_PASSWORD="${AMAZON_PASSWORD:-}"

echo "[INFO] Configuration:"
echo "[INFO]   - Log Level: ${LOG_LEVEL}"
echo "[INFO]   - Auth Timeout: ${AUTH_TIMEOUT}s"
echo "[INFO]   - Session Duration: ${SESSION_DURATION}s"
echo "[INFO]   - Keep-Alive Interval: ${KEEPALIVE_INTERVAL}s"
if [ -n "${AMAZON_EMAIL}" ]; then
    echo "[INFO]   - Auto Re-Login: configured"
else
    echo "[INFO]   - Auto Re-Login: not configured"
fi

# Ensure shared directory exists
mkdir -p /share/amazonparent
chmod 700 /share/amazonparent
echo "[INFO] Shared storage ready at /share/amazonparent"

# Kill any existing processes from previous runs
pkill -9 -f "x11vnc.*5904" 2>/dev/null || true
pkill -9 -f "fluxbox.*:100" 2>/dev/null || true
pkill -9 -f "Xvfb :100" 2>/dev/null || true

# Clean up stale X server files
rm -f /tmp/.X100-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X100 2>/dev/null || true
sleep 1

# Start Xvfb (virtual display)
echo "[INFO] Starting virtual display (Xvfb)..."
Xvfb :100 -screen 0 1280x1024x24 &
export DISPLAY=:100
sleep 2

# Start window manager
fluxbox &
sleep 1

# Start VNC server
echo "[INFO] Starting VNC server on port 5903..."
echo "[INFO] VNC password: amazonparent"
x11vnc -display :100 -forever -shared -rfbport 5903 -passwd amazonparent &

echo "[INFO] Starting FastAPI application..."

# Start the FastAPI application
cd /app || exit 1
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8100 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1
