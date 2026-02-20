# Amazon Parent Dashboard for Home Assistant

**Version**: 2.0.0

A complete Home Assistant solution for monitoring and controlling Amazon Parent Dashboard supervised devices (Fire tablets, Echo devices, Kindle devices).

Supports two deployment modes:
- **Docker Compose** (standalone) — run HA + auth sidecar with `docker compose up`
- **HA Supervisor Add-on** — install the add-on directly in HA OS/Supervised

## Overview

This project provides two components that work together:

1. **Authentication Sidecar** (`addon/`) — Browser-based authentication service using Playwright and VNC, with scheduled daily re-authentication to keep cookies fresh
2. **Custom Integration** (`custom_components/amazonparent/`) — Home Assistant integration for device control and monitoring

## Features

### Sensors
- Daily time limits (in minutes)
- Device count per child
- Curfew information (start/end times)
- Reading goal tracking

### Switches
- Pause/resume time limits (1 hour default)

### Buttons
- Quick pause: 15 minutes
- Quick pause: 30 minutes
- Quick pause: 1 hour

### Scheduled Re-Authentication
- Automatic full browser re-login every ~20 hours (configurable, randomized ±1h) to get fresh cookies
- Health checks every 4 hours — if cookies have expired, triggers immediate re-authentication
- Stealth browser automation with anti-detection measures (non-headless via Xvfb, human-like typing/clicking, stealth JS injection)
- Retry logic: up to 3 attempts with increasing backoff (5min, 15min, 30min)
- Manual reauth trigger via Web UI or API
- Session health monitoring via `/api/reauth/status`

---

## Installation — Docker Compose (Recommended)

This is the simplest way to run everything standalone, without HA OS or Supervisor.

### Prerequisites

- Docker and Docker Compose v2
- A VNC client for initial authentication

### Step 1: Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your Amazon credentials:

```
AMAZON_EMAIL=your-email@example.com
AMAZON_PASSWORD=your-password
```

These enable automatic re-authentication when cookies expire. If you omit them, the system still works but you'll need to manually re-authenticate via VNC when cookies expire (~24h).

### Step 2: Build and start

```bash
docker compose up -d
```

This starts two containers:
- `amazonparent-auth` — auth sidecar on ports 8100 (API/UI) and 5903 (VNC)
- `homeassistant` — Home Assistant on the host network

The HA container waits for the auth sidecar health check to pass before starting.

### Step 3: Initial authentication

1. Open `http://localhost:8100` in your browser
2. Click **Start Authentication (VNC)**
3. Connect to VNC at `localhost:5903` (password: `amazonparent`)
4. Sign in to Amazon in the browser window
5. Complete 2FA if prompted
6. The Web UI will show "Authentication successful" when done

### Step 4: Install the integration in HA

1. Copy `custom_components/amazonparent/` into your HA config directory:
   ```
   ./ha-config/custom_components/amazonparent/
   ```
2. Restart Home Assistant
3. Go to **Settings** > **Devices & Services** > **Add Integration**
4. Search for **Amazon Parent Dashboard**
5. Enter add-on URL: `http://amazonparent-auth:8100`

### Step 5: Verify re-authentication

After initial auth, the scheduled re-authentication system starts automatically:

```bash
# Check reauth status (next scheduled reauth, session health, etc.)
curl http://localhost:8100/api/reauth/status

# Manually trigger a full browser re-authentication
curl -X POST http://localhost:8100/api/reauth/trigger

# Run an immediate health check against Amazon API
curl -X POST http://localhost:8100/api/reauth/health-check

# Check overall service health
curl http://localhost:8100/api/health
```

You can also monitor the re-authentication panel in the Web UI at `http://localhost:8100`.

---

## Installation — HA Supervisor Add-on

### Prerequisites

- Home Assistant 2023.1 or newer with Supervisor
- A VNC client for initial authentication

### Step 1: Install Authentication Add-on

1. Copy the `addon/` folder to `/addons/amazonparent-playwright-ha/` in your Home Assistant configuration directory

2. Reload the add-on store:
   - Go to **Supervisor** > **Add-on Store** > **...** > **Reload**

3. Install the add-on:
   - Find "Amazon Parent Dashboard Auth" in the local add-ons list
   - Click **Install**
   - Start the add-on

4. Authenticate with Amazon:

   **a. Start the authentication process:**
   - Click "Open Web UI" or navigate to `http://[YOUR_HA_IP]:8100`
   - Click "Start Authentication (VNC)"

   **b. Install a VNC client (if you don't have one):**
   - **Windows**: Download [TigerVNC](https://github.com/TigerVNC/tigervnc/releases) or [RealVNC Viewer](https://www.realvnc.com/en/connect/download/viewer/)
   - **macOS**: Use built-in Screen Sharing (Finder > Cmd+K) or [RealVNC Viewer](https://www.realvnc.com/en/connect/download/viewer/)
   - **Linux**: Install via package manager: `sudo apt install tigervnc-viewer`
   - **Mobile**: Install "VNC Viewer" app from App Store or Google Play

   **c. Connect to the VNC server:**
   - Enter `[YOUR_HA_IP]:5903` and connect
   - **Password**: `amazonparent`

   **d. Sign in to Amazon:**
   - Enter your Amazon email and password in the browser window
   - Complete two-factor authentication if prompted
   - The add-on will automatically detect successful login and save cookies

   **e. Confirmation:**
   - Return to the add-on Web UI — you should see "Authentication successful!"

### Step 2: Install Custom Integration

1. Copy `custom_components/amazonparent/` to your HA `custom_components` directory:
   ```
   /config/custom_components/amazonparent/
   ```

2. Restart Home Assistant

3. Add the integration:
   - Go to **Settings** > **Devices & Services**
   - Click **Add Integration**
   - Search for "Amazon Parent Dashboard"
   - Enter add-on URL (default: `http://localhost:8100`)

---

## Configuration

### Environment Variables (Docker Compose)

| Variable | Default | Description |
|----------|---------|-------------|
| `AMAZON_EMAIL` | *(empty)* | Amazon account email for auto re-authentication |
| `AMAZON_PASSWORD` | *(empty)* | Amazon account password for auto re-authentication |
| `LOG_LEVEL` | `info` | Logging level (debug, info, warning, error) |
| `AUTH_TIMEOUT` | `300` | Timeout for manual VNC authentication in seconds |
| `SESSION_DURATION` | `86400` | Session duration in seconds |
| `REAUTH_INTERVAL` | `72000` | Base re-authentication interval in seconds (~20h), randomized ±1h |
| `HEALTH_CHECK_INTERVAL` | `14400` | Health check interval in seconds (4h) |
| `REAUTH_MAX_RETRIES` | `3` | Max retry attempts on reauth failure |

### Add-on Configuration Options (Supervisor)

- **log_level**: Set logging level (trace, debug, info, warning, error)
- **auth_timeout**: Timeout for authentication in seconds (60-600)
- **session_duration**: How long cookies remain valid (3600-604800 seconds)
- **reauth_interval**: Re-authentication interval in seconds (3600-172800)
- **health_check_interval**: Health check interval in seconds (1800-86400)
- **reauth_max_retries**: Max retry attempts (1-10)

For Supervisor, set `AMAZON_EMAIL` and `AMAZON_PASSWORD` as environment variables in the add-on configuration.

---

## Scheduled Re-Authentication

### How it works

1. **Reauth loop** — Every ~20 hours (randomized ±1h), the sidecar performs a full stealth browser login via Xvfb to obtain completely fresh cookies. This replaces the old heartbeat-based approach which couldn't reliably refresh cookies.
2. **Health check loop** — Every 4 hours, the sidecar hits Amazon's `get-household` API endpoint to verify cookies are still valid.
3. **Session healthy** (HTTP 200) — Cookies are valid, no action needed.
4. **Session expired** (HTTP 401/403) — If credentials are configured, triggers an immediate stealth browser re-authentication (up to 3 retries with backoff).
5. **2FA/CAPTCHA detected** — Auto reauth cannot solve these. The sidecar logs a warning and you'll need to re-authenticate manually via VNC.
6. **No credentials** — Without credentials, cookie expiry requires manual VNC re-authentication. The HA integration will show a persistent notification.

### Stealth Browser Login

The automated re-authentication uses several anti-detection techniques:
- Non-headless Chromium running on Xvfb (avoids headless detection)
- Stealth JavaScript injection (patches `navigator.webdriver`, `.plugins`, etc.)
- Human-like typing with random inter-key delays (50-150ms)
- Mouse movement to random points within elements before clicking
- Random delays between actions (1-5s)
- Visits `amazon.com` first before navigating to sign-in (natural flow)

### Monitoring

The Web UI at `http://localhost:8100` shows:
- Current session status (Healthy / Unhealthy / Unknown)
- Last reauth time and result (Success / Failed / Never)
- Next scheduled reauth time
- Last health check time
- Whether credentials are configured
- Buttons to trigger immediate reauth or health check

API endpoints:
- `GET /api/reauth/status` — JSON with session health, reauth times, failure count
- `POST /api/reauth/trigger` — Trigger immediate full browser re-authentication
- `POST /api/reauth/health-check` — Trigger immediate health check
- `GET /api/auth/mode` — Whether auto-login is available or manual-only
- `GET /api/health` — Overall health including `session_valid` and `next_reauth`

Legacy endpoints (backwards compatible):
- `GET /api/keepalive/status` — Alias for `/api/reauth/status`
- `POST /api/keepalive/trigger` — Alias that triggers a health check

---

## Usage Examples

### Automation: Pause Limits When Homework is Done

```yaml
automation:
  - alias: "Pause child's limits after homework"
    trigger:
      - platform: state
        entity_id: input_boolean.child_homework_complete
        to: "on"
    action:
      - service: button.press
        target:
          entity_id: button.child_name_pause_30min
```

### Script: Resume All Limits

```yaml
script:
  resume_all_limits:
    sequence:
      - service: switch.turn_off
        target:
          entity_id:
            - switch.child1_pause_limits
            - switch.child2_pause_limits
```

### Dashboard Card Example

```yaml
type: entities
title: Kids' Device Controls
entities:
  - sensor.child_name_daily_time_limit
  - sensor.child_name_device_count
  - switch.child_name_pause_limits
  - button.child_name_pause_15min
  - button.child_name_pause_30min
  - button.child_name_pause_1_hour
```

---

## Architecture

### Data Flow

```
User (VNC) --> Auth Sidecar (Playwright browser) --> Amazon login --> cookies saved encrypted
                    |
                    +--> Scheduled reauth (~20h) --> full stealth browser login --> fresh cookies
                    |       |
                    |       +--> Health check (4h) --> session expired? --> immediate reauth
                    |
HA Integration --> Auth Sidecar API (/api/cookies) --> cookies --> Amazon Parent Dashboard API
```

### Amazon API Endpoints

The integration communicates with Amazon Parent Dashboard API:

- `GET /get-household` — Fetch family members
- `GET /get-child-devices` — Fetch devices per child
- `GET /get-adjusted-time-limits` — Fetch schedules and limits
- `POST /set-offscreen-time` — Pause/resume time limits

### Auth Sidecar API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check with session status |
| `/api/cookies/check` | GET | Check if cookies exist |
| `/api/cookies` | GET | Retrieve stored cookies |
| `/api/cookies` | DELETE | Delete stored cookies |
| `/api/auth/start` | POST | Start VNC authentication flow |
| `/api/auth/status/{id}` | GET | Check auth session status |
| `/api/auth/mode` | GET | Auto-login available or manual-only |
| `/api/reauth/status` | GET | Scheduled reauth status |
| `/api/reauth/trigger` | POST | Trigger immediate re-authentication |
| `/api/reauth/health-check` | POST | Trigger immediate health check |

---

## Troubleshooting

### Integration won't load

1. Verify sidecar is running: `curl http://localhost:8100/api/health`
2. Check cookies exist: `curl http://localhost:8100/api/cookies/check`
3. Review Home Assistant logs for errors
4. Restart both sidecar and Home Assistant

### Authentication fails

1. Ensure VNC connection works at port 5903
2. Check sidecar logs: `docker logs amazonparent-auth`
3. Try increasing `AUTH_TIMEOUT`
4. Verify Amazon credentials are correct

### Session keeps expiring

1. Check reauth status: `curl http://localhost:8100/api/reauth/status`
2. Verify `AMAZON_EMAIL` and `AMAZON_PASSWORD` are set (required for auto reauth)
3. If auto reauth fails, check logs for 2FA/CAPTCHA messages: `docker logs amazonparent-auth`
4. Manually trigger a reauth: `curl -X POST http://localhost:8100/api/reauth/trigger`
5. Run a health check: `curl -X POST http://localhost:8100/api/reauth/health-check`

### Entities not updating

- Integration polls every 60 seconds
- Force update: Reload integration in UI
- Check network connectivity to Amazon
- Verify cookies haven't expired (check `/api/reauth/status`)

### Docker Compose issues

- **Build fails**: Ensure Docker has at least 4GB memory available (Playwright/Chromium is large)
- **Sidecar unhealthy**: Check `docker logs amazonparent-auth` for startup errors
- **HA can't reach sidecar**: Use `http://amazonparent-auth:8100` as the add-on URL (Docker service name)
- **VNC won't connect**: Ensure port 5903 is mapped and not firewalled

---

## Project Structure

```
HAamazonparent/
├── README.md
├── docker-compose.yaml               # Standalone Docker deployment
├── .env.example                       # Credential template
├── addon/                             # Authentication Sidecar
│   ├── Dockerfile
│   ├── config.json                    # HA add-on configuration
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                    # FastAPI app + Web UI
│   │   ├── config.py                  # Configuration (env vars)
│   │   ├── auth/
│   │   │   └── browser.py            # BrowserAuthManager + ScheduledReauthManager
│   │   └── storage/
│   │       └── file_storage.py        # Encrypted cookie storage
│   └── rootfs/                        # Container filesystem (s6-overlay)
└── custom_components/amazonparent/    # Home Assistant Integration
    ├── __init__.py                    # Integration setup
    ├── manifest.json
    ├── config_flow.py
    ├── coordinator.py                 # Data coordinator with auth retry
    ├── const.py
    ├── models.py
    ├── exceptions.py                  # Exception hierarchy
    ├── sensor.py
    ├── switch.py
    ├── button.py
    ├── auth/
    │   └── addon_client.py            # HTTP-only cookie client
    ├── client/
    │   └── api.py                     # Amazon API client
    └── translations/
```

---

## Known Limitations

1. **Child-centric control**: API controls all of a child's devices together (not per-device)
2. **Polling only**: No real-time push updates (60-second refresh interval)
3. **Unofficial API**: Uses reverse-engineered Amazon endpoints that may change
4. **2FA/CAPTCHA**: Auto re-authentication cannot solve these — requires one-time manual VNC auth
5. **Single region**: Hardcoded to `amazon.com` (US)

## Security Considerations

This integration is designed for home use on **trusted local networks**:

- **Encrypted Storage**: Amazon session cookies are encrypted at rest with Fernet
- **Credentials in env vars**: `AMAZON_EMAIL`/`AMAZON_PASSWORD` are passed via environment variables, never written to disk. Use `.env` (gitignored) or Docker secrets
- **VNC Access**: VNC password (`amazonparent`) is for local use only — do not expose port 5903 to the internet
- **Isolated Container**: Sidecar runs in its own Docker container
- **No Internet Exposure**: Do NOT expose ports 8100 or 5903 to the internet. Use a VPN (WireGuard, Tailscale) for remote access

For detailed security information, see [SECURITY.md](SECURITY.md).

## Support

- **Issues**: https://github.com/ricslash/HAamazonparent/issues
- **Discussions**: https://github.com/ricslash/HAamazonparent/discussions

## License

MIT License

## Disclaimer

**Important**: This integration uses unofficial, reverse-engineered Amazon API endpoints. Use at your own risk. This may violate Amazon's Terms of Service and could result in account restrictions. The authors are not responsible for any issues arising from the use of this integration.

This project is not affiliated with, endorsed by, or sponsored by Amazon.com, Inc. or its affiliates.
