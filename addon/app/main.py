"""Main FastAPI application for Amazon Parent Dashboard Auth."""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from auth.browser import BrowserAuthManager
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
    version="1.0.0"
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


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global browser_manager
    _LOGGER.info("Starting Amazon Parent Dashboard Auth Service v1.0.0")
    _LOGGER.info(f"Configuration: log_level={config.log_level}, auth_timeout={config.auth_timeout}s")

    try:
        browser_manager = BrowserAuthManager(auth_timeout=config.auth_timeout)
        await browser_manager.initialize()
        _LOGGER.info("Service started successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    _LOGGER.info("Shutting down Amazon Parent Dashboard Auth Service")
    if browser_manager:
        await browser_manager.cleanup()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main authentication interface."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amazon Parent Dashboard Authentication</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #ff9a56 0%, #ff6a00 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
            line-height: 1.5;
        }

        .status {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }

        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .status.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        button {
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
        }

        button:hover:not(:disabled) {
            background: #e88b00;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(255, 153, 0, 0.4);
        }

        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .instructions {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }

        .instructions h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 16px;
        }

        .instructions ol {
            margin-left: 20px;
            color: #666;
            font-size: 14px;
            line-height: 1.8;
        }

        .instructions li {
            margin-bottom: 8px;
        }

        .loader {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #ff9900;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .info-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
            font-size: 14px;
            color: #856404;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ðŸ” Amazon Parent Dashboard</h1>
        <p class="subtitle">Authentication service for Home Assistant integration</p>

        <div id="status" class="status"></div>

        <button id="authButton" onclick="startAuth()">
            Start Authentication
        </button>

        <div class="instructions">
            <h3>ðŸ“‹ Instructions</h3>
            <ol>
                <li>Click "Start Authentication"</li>
                <li>A browser window will open with Amazon login page</li>
                <li>Sign in with your Amazon account</li>
                <li>Complete two-factor authentication if prompted</li>
                <li>Wait for the success message</li>
                <li>Return to Home Assistant to complete configuration</li>
            </ol>
        </div>

        <div class="info-box">
            ðŸ’¡ <strong>Note:</strong> The browser window may take a few seconds to appear. Do not close this page during authentication.
        </div>
    </div>

    <script>
        let sessionId = null;
        let statusCheckInterval = null;

        async function startAuth() {
            const button = document.getElementById('authButton');
            const status = document.getElementById('status');

            button.disabled = true;
            button.innerHTML = '<div class="loader"></div><span>Starting...</span>';

            try {
                showStatus("ðŸ”„ Starting authentication...", "info");

                const response = await fetch('/api/auth/start', {
                    method: 'POST'
                });

                if (!response.ok) {
                    throw new Error("Failed to start authentication");
                }

                const data = await response.json();
                sessionId = data.session_id;

                showStatus("ðŸŒ Browser window opened. Please sign in to Amazon...", "info");
                button.innerHTML = '<div class="loader"></div><span>Waiting for login...</span>';

                // Start checking status
                statusCheckInterval = setInterval(checkAuthStatus, 2000);

            } catch (error) {
                showStatus("âŒ Failed to start: " + error.message, "error");
                button.disabled = false;
                button.innerHTML = 'Retry';
            }
        }

        async function checkAuthStatus() {
            if (!sessionId) return;

            try {
                const response = await fetch(`/api/auth/status/${sessionId}`);
                const data = await response.json();

                if (data.status === 'completed') {
                    clearInterval(statusCheckInterval);
                    let message = `âœ… Authentication successful! ${data.cookie_count} cookies saved.`;
                    if (data.has_csrf_token) {
                        message += `\\nâœ“ CSRF token extracted.`;
                    }
                    message += `\\n\\nYou can now complete the setup in Home Assistant.`;

                    showStatus(message, 'success');

                    const button = document.getElementById('authButton');
                    button.innerHTML = 'âœ“ Authentication Complete';
                    button.style.background = '#28a745';

                } else if (data.status === 'timeout') {
                    clearInterval(statusCheckInterval);
                    showStatus("â±ï¸ Authentication timeout. Please try again.", "error");

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = "Retry Authentication";

                } else if (data.status === 'error') {
                    clearInterval(statusCheckInterval);
                    showStatus("âŒ Error: " + (data.error || "Unknown error"), "error");

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = "Retry Authentication";
                }

            } catch (error) {
                console.error('Status check failed:', error);
            }
        }

        function showStatus(message, type) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = `status ${type}`;
            status.style.display = 'block';
        }

        // Check if cookies already exist
        window.addEventListener('load', async () => {
            try {
                const response = await fetch('/api/cookies/check');
                const data = await response.json();

                if (data.exists) {
                    showStatus("âœ“ Cookies are already saved. You can configure the integration in Home Assistant.", "success");
                }
            } catch (error) {
                // Ignore errors on initial check
            }
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "amazonparent-auth",
        "version": "1.0.0"
    }


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


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower()
    )
