"""Main FastAPI application for Amazon Parent Dashboard Auth."""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from auth.browser import BrowserAuthManager, ScheduledReauthManager
from storage.file_storage import SharedStorage
from config import get_config

# Configure logging
config = get_config()
logging.basicConfig(
    level=config.log_level.upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

_LOGGER = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Amazon Parent Dashboard Auth Service",
    description="Authentication service for Amazon Parent Dashboard integration",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
storage = SharedStorage(config.share_dir)
browser_manager = None
reauth_manager = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global browser_manager, reauth_manager
    _LOGGER.info("Starting Amazon Parent Dashboard Auth Service v2.0.0")
    _LOGGER.info(
        f"Configuration: log_level={config.log_level}, auth_timeout={config.auth_timeout}s, "
        f"reauth_interval={config.reauth_interval}s, health_check_interval={config.health_check_interval}s"
    )

    try:
        browser_manager = BrowserAuthManager(auth_timeout=config.auth_timeout)
        await browser_manager.initialize()

        # Start scheduled reauth manager
        reauth_manager = ScheduledReauthManager(
            storage=storage,
            browser_auth_manager=browser_manager,
            reauth_interval=config.reauth_interval,
            health_check_interval=config.health_check_interval,
            max_retries=config.reauth_max_retries,
            amazon_email=config.amazon_email,
            amazon_password=config.amazon_password,
        )
        reauth_manager.start()

        _LOGGER.info("Service started successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    _LOGGER.info("Shutting down Amazon Parent Dashboard Auth Service")
    if reauth_manager:
        await reauth_manager.stop()
    if browser_manager:
        await browser_manager.cleanup()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main authentication interface."""
    credentials_configured = bool(config.amazon_email and config.amazon_password)
    reauth_interval_hours = round(config.reauth_interval / 3600, 1)
    health_check_hours = round(config.health_check_interval / 3600, 1)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amazon Parent Dashboard Authentication</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #ff9a56 0%, #ff6a00 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}

        .container {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 600px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}

        h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }}

        h2 {{
            color: #333;
            margin-bottom: 15px;
            font-size: 20px;
            margin-top: 25px;
        }}

        .subtitle {{
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
            line-height: 1.5;
        }}

        .status {{
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }}

        .status.success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}

        .status.error {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}

        .status.info {{
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }}

        button {{
            width: 100%;
            padding: 16px;
            background: #ff9900;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }}

        button:hover:not(:disabled) {{
            background: #e88b00;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(255, 153, 0, 0.4);
        }}

        button:disabled {{
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }}

        button.secondary {{
            background: #6c757d;
            margin-top: 10px;
        }}

        button.secondary:hover:not(:disabled) {{
            background: #545b62;
            box-shadow: 0 4px 12px rgba(108, 117, 125, 0.4);
        }}

        .instructions {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}

        .instructions h3 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 16px;
        }}

        .instructions ol {{
            margin-left: 20px;
            color: #666;
            font-size: 14px;
            line-height: 1.8;
        }}

        .instructions li {{
            margin-bottom: 8px;
        }}

        .loader {{
            border: 3px solid #f3f3f3;
            border-top: 3px solid #ff9900;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
        }}

        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}

        .info-box {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
            font-size: 14px;
            color: #856404;
        }}

        .reauth-panel {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
            border: 1px solid #e9ecef;
        }}

        .reauth-panel .stat {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e9ecef;
            font-size: 14px;
        }}

        .reauth-panel .stat:last-child {{
            border-bottom: none;
        }}

        .reauth-panel .stat .label {{
            color: #666;
        }}

        .reauth-panel .stat .value {{
            color: #333;
            font-weight: 600;
        }}

        .button-row {{
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }}

        .button-row button {{
            flex: 1;
        }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}

        .badge.healthy {{
            background: #d4edda;
            color: #155724;
        }}

        .badge.unhealthy {{
            background: #f8d7da;
            color: #721c24;
        }}

        .badge.unknown {{
            background: #e2e3e5;
            color: #383d41;
        }}

        .badge.configured {{
            background: #d1ecf1;
            color: #0c5460;
        }}

        .badge.not-configured {{
            background: #e2e3e5;
            color: #383d41;
        }}

        .badge.success {{
            background: #d4edda;
            color: #155724;
        }}

        .badge.failed {{
            background: #f8d7da;
            color: #721c24;
        }}

        .badge.never {{
            background: #e2e3e5;
            color: #383d41;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Amazon Parent Dashboard</h1>
        <p class="subtitle">Authentication service for Home Assistant integration</p>

        <div id="status" class="status"></div>

        <button id="authButton" onclick="startAuth()">
            Start Authentication (VNC)
        </button>

        <h2>Daily Re-Authentication</h2>
        <div class="reauth-panel" id="reauthPanel">
            <div class="stat">
                <span class="label">Session Status</span>
                <span class="value" id="sessionStatus"><span class="badge unknown">Checking...</span></span>
            </div>
            <div class="stat">
                <span class="label">Last Reauth</span>
                <span class="value" id="lastReauth">--</span>
            </div>
            <div class="stat">
                <span class="label">Last Result</span>
                <span class="value" id="lastResult"><span class="badge never">Never</span></span>
            </div>
            <div class="stat">
                <span class="label">Next Reauth</span>
                <span class="value" id="nextReauth">--</span>
            </div>
            <div class="stat">
                <span class="label">Last Health Check</span>
                <span class="value" id="lastHealthCheck">--</span>
            </div>
            <div class="stat">
                <span class="label">Reauth Interval</span>
                <span class="value">~{reauth_interval_hours}h (health check every {health_check_hours}h)</span>
            </div>
            <div class="stat">
                <span class="label">Credentials</span>
                <span class="value">
                    <span class="badge {'configured' if credentials_configured else 'not-configured'}">
                        {'Configured' if credentials_configured else 'Not Configured'}
                    </span>
                </span>
            </div>
            <div class="button-row">
                <button class="secondary" onclick="triggerReauth()">Trigger Reauth Now</button>
                <button class="secondary" onclick="triggerHealthCheck()">Health Check</button>
            </div>
        </div>

        <div class="instructions">
            <h3>Instructions</h3>
            <ol>
                <li>Click "Start Authentication (VNC)" for initial login</li>
                <li>A browser window will open with Amazon login page</li>
                <li>Connect via VNC (port 5903) to see the browser</li>
                <li>Sign in with your Amazon account</li>
                <li>Complete two-factor authentication if prompted</li>
                <li>Wait for the success message</li>
                <li>Return to Home Assistant to complete configuration</li>
            </ol>
        </div>

        <div class="info-box">
            <strong>Note:</strong> The system automatically re-authenticates every ~{reauth_interval_hours} hours using a full browser login to keep cookies fresh.
            Health checks run every {health_check_hours} hours and trigger an immediate reauth if cookies have expired.
            {'Credentials are configured - automatic re-authentication is active.' if credentials_configured else 'Set AMAZON_EMAIL and AMAZON_PASSWORD environment variables to enable automatic re-authentication.'}
        </div>
    </div>

    <script>
        let sessionId = null;
        let statusCheckInterval = null;

        async function startAuth() {{
            const button = document.getElementById('authButton');
            const status = document.getElementById('status');

            button.disabled = true;
            button.innerHTML = '<div class="loader"></div><span>Starting...</span>';

            try {{
                showStatus("Starting authentication...", "info");

                const response = await fetch('/api/auth/start', {{
                    method: 'POST'
                }});

                if (!response.ok) {{
                    throw new Error("Failed to start authentication");
                }}

                const data = await response.json();
                sessionId = data.session_id;

                showStatus("Browser window opened. Please sign in via VNC (port 5903)...", "info");
                button.innerHTML = '<div class="loader"></div><span>Waiting for login...</span>';

                statusCheckInterval = setInterval(checkAuthStatus, 2000);

            }} catch (error) {{
                showStatus("Failed to start: " + error.message, "error");
                button.disabled = false;
                button.innerHTML = 'Retry';
            }}
        }}

        async function checkAuthStatus() {{
            if (!sessionId) return;

            try {{
                const response = await fetch(`/api/auth/status/${{sessionId}}`);
                const data = await response.json();

                if (data.status === 'completed') {{
                    clearInterval(statusCheckInterval);
                    let message = `Authentication successful! ${{data.cookie_count}} cookies saved.`;
                    if (data.has_csrf_token) {{
                        message += ` CSRF token extracted.`;
                    }}
                    message += ` You can now complete the setup in Home Assistant.`;

                    showStatus(message, 'success');

                    const button = document.getElementById('authButton');
                    button.innerHTML = 'Authentication Complete';
                    button.style.background = '#28a745';
                    refreshReauthStatus();

                }} else if (data.status === 'timeout') {{
                    clearInterval(statusCheckInterval);
                    showStatus("Authentication timeout. Please try again.", "error");

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = "Retry Authentication";

                }} else if (data.status === 'error') {{
                    clearInterval(statusCheckInterval);
                    showStatus("Error: " + (data.error || "Unknown error"), "error");

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = "Retry Authentication";
                }}

            }} catch (error) {{
                console.error('Status check failed:', error);
            }}
        }}

        async function triggerReauth() {{
            try {{
                showStatus("Triggering re-authentication (this may take up to 2 minutes)...", "info");
                const response = await fetch('/api/reauth/trigger', {{ method: 'POST' }});
                const data = await response.json();

                if (data.result && data.result.status === 'success') {{
                    showStatus("Re-authentication successful! Fresh cookies saved.", "success");
                }} else if (data.result && data.result.status === 'already_running') {{
                    showStatus("A re-authentication is already in progress.", "info");
                }} else if (data.result && data.result.status === 'error') {{
                    showStatus("Reauth error: " + (data.result.error || "Unknown"), "error");
                }} else {{
                    showStatus("Reauth result: " + JSON.stringify(data.result), "error");
                }}
                refreshReauthStatus();
            }} catch (error) {{
                showStatus("Failed to trigger reauth: " + error.message, "error");
            }}
        }}

        async function triggerHealthCheck() {{
            try {{
                showStatus("Running health check...", "info");
                const response = await fetch('/api/reauth/health-check', {{ method: 'POST' }});
                const data = await response.json();

                if (data.result && data.result.status === 'healthy') {{
                    showStatus("Health check passed - session is healthy!", "success");
                }} else if (data.result && data.result.status === 'expired') {{
                    showStatus("Health check: session expired (HTTP " + data.result.http_status + "). Reauth recommended.", "error");
                }} else if (data.result && data.result.status === 'no_cookies') {{
                    showStatus("Health check: no cookies stored. Please authenticate first.", "error");
                }} else {{
                    showStatus("Health check result: " + JSON.stringify(data.result), "info");
                }}
                refreshReauthStatus();
            }} catch (error) {{
                showStatus("Failed to run health check: " + error.message, "error");
            }}
        }}

        async function refreshReauthStatus() {{
            try {{
                const response = await fetch('/api/reauth/status');
                const data = await response.json();

                const statusEl = document.getElementById('sessionStatus');
                if (data.session_healthy) {{
                    statusEl.innerHTML = '<span class="badge healthy">Healthy</span>';
                }} else if (data.last_health_check) {{
                    statusEl.innerHTML = '<span class="badge unhealthy">Unhealthy</span>';
                }} else {{
                    statusEl.innerHTML = '<span class="badge unknown">Unknown</span>';
                }}

                document.getElementById('lastReauth').textContent =
                    data.last_reauth ? new Date(data.last_reauth).toLocaleString() : '--';

                const resultEl = document.getElementById('lastResult');
                if (data.last_reauth_result === 'success') {{
                    resultEl.innerHTML = '<span class="badge success">Success</span>';
                }} else if (data.last_reauth_result === 'failed') {{
                    resultEl.innerHTML = '<span class="badge failed">Failed</span>';
                }} else {{
                    resultEl.innerHTML = '<span class="badge never">Never</span>';
                }}

                document.getElementById('nextReauth').textContent =
                    data.next_reauth ? new Date(data.next_reauth).toLocaleString() : '--';

                document.getElementById('lastHealthCheck').textContent =
                    data.last_health_check ? new Date(data.last_health_check).toLocaleString() : '--';

            }} catch (error) {{
                console.error('Failed to refresh reauth status:', error);
            }}
        }}

        function showStatus(message, type) {{
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = `status ${{type}}`;
            status.style.display = 'block';
        }}

        // Check initial state on load
        window.addEventListener('load', async () => {{
            try {{
                const response = await fetch('/api/cookies/check');
                const data = await response.json();

                if (data.exists) {{
                    showStatus("Cookies are already saved. You can configure the integration in Home Assistant.", "success");
                }}
            }} catch (error) {{
                // Ignore errors on initial check
            }}

            refreshReauthStatus();
            // Refresh reauth status every 30 seconds
            setInterval(refreshReauthStatus, 30000);
        }});
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    status_data = {
        "status": "healthy",
        "service": "amazonparent-auth",
        "version": "2.0.0",
        "credentials_configured": bool(config.amazon_email and config.amazon_password),
    }

    if reauth_manager:
        ra_status = reauth_manager.get_status()
        status_data["session_valid"] = ra_status["session_healthy"]
        status_data["last_reauth"] = ra_status["last_reauth"]
        status_data["next_reauth"] = ra_status["next_reauth"]

    return status_data


@app.post("/api/auth/start")
async def start_authentication():
    """Start browser authentication flow."""
    try:
        session_id = await browser_manager.start_auth_session()
        _LOGGER.info(f"Started auth session: {session_id}")
        return {
            "session_id": session_id,
            "status": "started",
            "message": "Authentication session started"
        }
    except Exception as e:
        _LOGGER.error(f"Failed to start auth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/status/{session_id}")
async def check_auth_status(session_id: str):
    """Check authentication status."""
    status = await browser_manager.get_session_status(session_id)
    return status


@app.get("/api/auth/mode")
async def auth_mode():
    """Return whether auto-login is available or manual-only."""
    return {
        "auto_login_available": bool(config.amazon_email and config.amazon_password),
        "mode": "auto" if (config.amazon_email and config.amazon_password) else "manual",
    }


@app.get("/api/cookies/check")
async def check_cookies():
    """Check if cookies exist."""
    exists = await storage.check_exists()
    return {"exists": exists}


@app.get("/api/cookies")
async def get_cookies():
    """Retrieve stored cookies (for integration)."""
    try:
        cookies = await storage.load_cookies()
        return {
            "cookies": cookies,
            "status": "success",
            "count": len(cookies)
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No cookies found")
    except Exception as e:
        _LOGGER.error(f"Failed to load cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cookies")
async def delete_cookies():
    """Delete stored cookies."""
    try:
        await storage.clear_cookies()
        return {"status": "success", "message": "Cookies deleted"}
    except Exception as e:
        _LOGGER.error(f"Failed to delete cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cookies/info")
async def cookies_info():
    """Return cookie metadata without decrypting (cheap check for integration polling)."""
    exists = await storage.check_exists()
    last_reauth = None
    if reauth_manager:
        status = reauth_manager.get_status()
        last_reauth = status.get("last_reauth")
    return {
        "exists": exists,
        "last_updated": last_reauth,
    }


@app.get("/api/reauth/status")
async def reauth_status():
    """Get scheduled re-authentication status."""
    if not reauth_manager:
        raise HTTPException(status_code=503, detail="Reauth manager not initialized")
    return reauth_manager.get_status()


@app.post("/api/reauth/trigger")
async def reauth_trigger():
    """Manually trigger an immediate re-authentication."""
    if not reauth_manager:
        raise HTTPException(status_code=503, detail="Reauth manager not initialized")
    result = await reauth_manager.trigger_reauth()
    return {"status": "triggered", "result": result}


@app.post("/api/reauth/health-check")
async def reauth_health_check():
    """Manually trigger an immediate health check."""
    if not reauth_manager:
        raise HTTPException(status_code=503, detail="Reauth manager not initialized")
    result = await reauth_manager.trigger_health_check()
    return {"status": "checked", "result": result}


# Keep old endpoints as aliases for backwards compatibility
@app.get("/api/keepalive/status")
async def keepalive_status():
    """Legacy endpoint - redirects to reauth status."""
    return await reauth_status()


@app.post("/api/keepalive/trigger")
async def keepalive_trigger():
    """Legacy endpoint - triggers health check."""
    if not reauth_manager:
        raise HTTPException(status_code=503, detail="Reauth manager not initialized")
    result = await reauth_manager.trigger_health_check()
    return {"status": "triggered", "result": result}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower()
    )
