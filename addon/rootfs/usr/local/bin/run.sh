#!/usr/bin/with-contenv bashio
# ==============================================================================
# Start Amazon Parent Dashboard Auth Service
# ==============================================================================

bashio::log.info "Starting Amazon Parent Dashboard Auth Service..."

# Read configuration from Home Assistant
LOG_LEVEL=$(bashio::config 'log_level' 'info')
AUTH_TIMEOUT=$(bashio::config 'auth_timeout' '300')
SESSION_DURATION=$(bashio::config 'session_duration' '86400')

# Export environment variables
export LOG_LEVEL="${LOG_LEVEL}"
export AUTH_TIMEOUT="${AUTH_TIMEOUT}"
export SESSION_DURATION="${SESSION_DURATION}"

bashio::log.info "Configuration loaded:"
bashio::log.info "  - Log Level: ${LOG_LEVEL}"
bashio::log.info "  - Auth Timeout: ${AUTH_TIMEOUT}s"
bashio::log.info "  - Session Duration: ${SESSION_DURATION}s"

# Ensure shared directory exists
mkdir -p /share/amazonparent
chmod 700 /share/amazonparent

bashio::log.info "Shared storage ready at /share/amazonparent"

# Start Xvfb (virtual display)
bashio::log.info "Starting virtual display (Xvfb)..."

# Kill any existing processes from previous runs
pkill -9 -f "x11vnc.*5904" 2>/dev/null || true
pkill -9 -f "fluxbox.*:100" 2>/dev/null || true
pkill -9 -f "Xvfb :100" 2>/dev/null || true

# Clean up any stale X server files
rm -f /tmp/.X100-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X100 2>/dev/null || true

# Wait for processes to fully terminate
sleep 1

# Start Xvfb
Xvfb :100 -screen 0 1280x1024x24 &
export DISPLAY=:100

# Wait for Xvfb to start
sleep 2

# Start window manager
fluxbox &

# Wait for window manager to initialize
sleep 1

# Start VNC server for remote access
bashio::log.info "Starting VNC server on port 5903..."
bashio::log.info "VNC password: amazonparent"
x11vnc -display :100 -forever -shared -rfbport 5903 -passwd amazonparent &

bashio::log.info "Starting FastAPI application..."

# Start the FastAPI application with uvicorn directly
cd /app || exit 1
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8100 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1