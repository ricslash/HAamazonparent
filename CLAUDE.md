# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Amazon Parent Dashboard for Home Assistant — a two-component system for monitoring and controlling Amazon Kids parental controls (Fire tablets, Echo devices, Kindle) from Home Assistant.

## Architecture

### Canonical Directories

1. **`addon/`** — Authentication sidecar (FastAPI + Playwright + VNC). Runs as an HA Supervisor add-on or standalone Docker container. Handles browser-based Amazon login, cookie extraction, encrypted cookie storage, and scheduled re-authentication. Exposes API on port 8100 and VNC on port 5903.

2. **`custom_components/amazonparent/`** — Home Assistant custom integration. Uses `aiohttp` to call Amazon's unofficial Parent Dashboard API with cookies obtained from the sidecar.

### Non-canonical Directories (legacy/dev copies)

- **`amazonparent/`** — Development copy that mirrors `custom_components/amazonparent/`. When editing integration code, **always edit `custom_components/amazonparent/` first** — it is the canonical source.
- **`amazonparent-playwright-ha/`** — Older copy of the add-on. The canonical add-on is `addon/`.

### Data Flow

```
User (VNC) → addon (Playwright browser) → Amazon login → cookies saved encrypted
                  |
                  +-→ Scheduled reauth (~20h) → full stealth browser login → fresh cookies
                  |       +-→ Health check (4h) → session expired? → immediate reauth
                  |
HA integration → addon API (/api/cookies) → cookies → Amazon Parent Dashboard API
```

### Key Integration Components

- **`coordinator.py`** — `DataUpdateCoordinator` subclass. Polls Amazon API every 60s. Handles session expiry with one automatic cookie refresh retry before creating a persistent notification.
- **`client/api.py`** — `AmazonParentAPIClient`. Manages aiohttp session with Amazon cookies. CSRF token (`ft-panda-csrf-token`) required for all requests.
- **`auth/addon_client.py`** — `AddonCookieClient`. HTTP client that fetches cookies from the sidecar's `/api/cookies` endpoint.
- **`models.py`** — Dataclasses: `HouseholdMember`, `Device`, `ChildSchedule`, `DaySchedule`, `CurfewConfig`, `TimeLimits`, `GoalsConfig`.
- **`config_flow.py`** — Config flow that connects to the sidecar URL (default `http://localhost:8100`).
- **Platforms**: `sensor.py`, `switch.py`, `button.py` — entities for time limits, device counts, curfew info, pause/resume controls.

### Integration Setup Chain

`__init__.py:async_setup_entry` → `AddonCookieClient` loads cookies → `AmazonParentAPIClient` created with cookies → CSRF token verified → `AmazonParentDataUpdateCoordinator` performs first refresh → platforms forwarded.

### Add-on Components

- **`app/main.py`** — FastAPI app with auth endpoints and inline HTML UI.
- **`app/auth/browser.py`** — `BrowserAuthManager` (Playwright automation, stealth reauth) + `ScheduledReauthManager` (periodic browser re-authentication and health checks).
- **`app/storage/file_storage.py`** — Fernet-encrypted cookie storage at `/share/amazonparent/`.
- **`app/config.py`** — Configuration from environment variables.
- **`rootfs/`** — s6-overlay service scripts; `run.sh` starts Xvfb + fluxbox + x11vnc + uvicorn.

## Build & Run Commands

### Docker Compose (standalone)

```bash
cp .env.example .env        # Configure AMAZON_EMAIL and AMAZON_PASSWORD
docker compose up -d         # Builds addon, starts HA + auth sidecar
docker compose up -d --build # Rebuild after code changes
docker logs amazonparent-auth  # View sidecar logs
```

### Add-on Only (for testing sidecar changes)

```bash
docker build -t amazonparent-auth ./addon
docker run -p 8100:8100 -p 5903:5903 --shm-size=2gb amazonparent-auth
```

### No test suite or linter/formatter configuration exists yet.

## Amazon API

All requests go to `https://www.amazon.com/parentdashboard/ajax`:
- `GET /get-household` — family members
- `GET /get-child-devices` — devices per child
- `GET /get-adjusted-time-limits?childDirectedId=...` — schedules/limits
- `POST /set-offscreen-time` — pause/resume limits (body: `{directedIds, expirationTimeInSeconds}`)
- `POST /set-time-limit-v2` — set time limits

API controls are child-centric (all devices for a child, not per-device). The integration uses unofficial reverse-engineered endpoints — API shapes may change without notice.

## Auth Sidecar API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check with session status |
| `/api/cookies/check` | GET | Check if cookies exist |
| `/api/cookies` | GET | Retrieve stored cookies |
| `/api/cookies` | DELETE | Delete stored cookies |
| `/api/auth/start` | POST | Start VNC authentication flow |
| `/api/auth/status/{id}` | GET | Check auth session status |
| `/api/auth/mode` | GET | Auto-login available or manual-only |
| `/api/reauth/status` | GET | Scheduled reauth status (next reauth, health, etc.) |
| `/api/reauth/trigger` | POST | Trigger immediate browser re-authentication |
| `/api/reauth/health-check` | POST | Trigger immediate session health check |
| `/api/keepalive/status` | GET | Legacy alias for `/api/reauth/status` |
| `/api/keepalive/trigger` | POST | Legacy alias — triggers health check |

## Development Notes

- The add-on runs in a Debian-based Docker container (built from `ghcr.io/hassio-addons/debian-base:7.3.3`). Requires `--shm-size=2gb` for Chromium.
- Add-on Python deps in `addon/requirements.txt`: `fastapi`, `uvicorn`, `cryptography`, `python-multipart`, `aiohttp`. Playwright is installed separately in the Dockerfile.
- Integration deps (in `manifest.json`): `aiohttp>=3.9.0`, `cryptography>=41.0.0`.
- Scheduled reauth configurable via `REAUTH_INTERVAL` (default 72000s = ~20h), `HEALTH_CHECK_INTERVAL` (default 14400s = 4h), `REAUTH_MAX_RETRIES` (default 3).
- Auto re-login requires `AMAZON_EMAIL` and `AMAZON_PASSWORD` env vars; cannot solve 2FA/CAPTCHA.
- Hardcoded to `amazon.com` (US region only).
