# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Amazon Parent Dashboard for Home Assistant — a two-component system for monitoring and controlling Amazon Kids parental controls (Fire tablets, Echo devices, Kindle) from Home Assistant.

## Architecture

The project has three directories that contain code, but only two are canonical:

1. **`addon/`** — Authentication add-on (FastAPI + Playwright + VNC). Runs as an HA Supervisor add-on in Docker. Handles browser-based Amazon login, cookie extraction, and encrypted cookie storage. Exposes API on port 8100 and VNC on port 5903.

2. **`custom_components/amazonparent/`** — Home Assistant custom integration. This is the canonical copy of the HA integration code. Uses `aiohttp` to call Amazon's unofficial Parent Dashboard API with cookies obtained from the add-on.

3. **`amazonparent/`** — Development copy of the integration (mirrors `custom_components/amazonparent/` but adds `auth/addon_client.py` and `exceptions.py`). Contains auth client code that the custom_components version imports from.

4. **`amazonparent-playwright-ha/`** — Older copy of the add-on code. The canonical add-on is `addon/`.

### Data Flow

```
User (VNC) → addon (Playwright browser) → Amazon login → cookies saved encrypted
HA integration → addon API (/api/cookies) → cookies → Amazon Parent Dashboard API
```

### Key Integration Components

- **`coordinator.py`** — `DataUpdateCoordinator` subclass. Polls Amazon API every 60s. Handles session expiry with one automatic cookie refresh retry before notifying user.
- **`client/api.py`** — `AmazonParentAPIClient`. Manages aiohttp session with Amazon cookies. CSRF token (`ft-panda-csrf-token`) required for all requests.
- **`models.py`** — Dataclasses: `HouseholdMember`, `Device`, `ChildSchedule`, `DaySchedule`, `CurfewConfig`, `TimeLimits`, `GoalsConfig`.
- **`config_flow.py`** — Config flow that connects to the add-on URL (default `http://localhost:8100`).
- **Platforms**: `sensor.py`, `switch.py`, `button.py` — entities for time limits, device counts, curfew info, pause/resume controls.

### Add-on Components

- **`app/main.py`** — FastAPI app with auth endpoints and inline HTML UI.
- **`app/auth/browser.py`** — Playwright browser automation for Amazon login.
- **`app/storage/file_storage.py`** — Encrypted cookie storage at `/share/amazonparent/`.
- **`rootfs/`** — s6-overlay service scripts, `run.sh` starts Xvfb + fluxbox + x11vnc + uvicorn.

## Amazon API

All requests go to `https://www.amazon.com/parentdashboard/ajax` with these endpoints:
- `GET /get-household` — family members
- `GET /get-child-devices` — devices per child
- `GET /get-adjusted-time-limits?childDirectedId=...` — schedules/limits
- `POST /set-offscreen-time` — pause/resume limits (body: `{directedIds, expirationTimeInSeconds}`)

API controls are child-centric (all devices for a child, not per-device).

## Development Notes

- The add-on runs in a Debian-based Docker container (built from `ghcr.io/hassio-addons/debian-base:7.3.3`).
- Add-on Python deps: `fastapi`, `uvicorn`, `cryptography`, `python-multipart`, `playwright`.
- Integration deps (in `manifest.json`): `aiohttp>=3.9.0`, `cryptography>=41.0.0`.
- No test suite exists yet.
- No linter/formatter configuration exists yet.
- The integration uses unofficial reverse-engineered Amazon endpoints — API shapes may change without notice.
