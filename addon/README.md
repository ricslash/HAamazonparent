# Amazon Parent Dashboard Authentication Add-on

Provides browser-based authentication for Amazon Parent Dashboard integration.

## Installation

1. Copy this folder to `/addons/amazonparent-playwright-ha/` in your Home Assistant config
2. Go to **Supervisor** â†’ **Add-on Store** â†’ **â‹®** â†’ **Reload**
3. Find "Amazon Parent Dashboard Auth" in the local add-ons list
4. Click **Install**
5. Start the add-on
6. Open the Web UI to authenticate

## Configuration

- **log_level**: Set logging level (trace, debug, info, warning, error)
- **auth_timeout**: Timeout for authentication in seconds (60-600)
- **session_duration**: How long cookies remain valid (3600-604800 seconds)

## How to Use

1. Start the add-on
2. Click "Open Web UI" or go to http://[YOUR_HA_IP]:8100
3. Click "Start Authentication"
4. **Open noVNC** in your browser (or click the **noVNC** link in the Web UI): `http://[YOUR_HA_IP]:6080/vnc.html`
   - Password: `amazonparent`
5. Sign in to Amazon in the noVNC browser
6. Wait for success message
7. Configure the Amazon Parent Dashboard integration

## Ports

- **8100**: Web UI and API
- **6080**: noVNC web client (proxies to localhost-only VNC on `127.0.0.1:5903`, password: `amazonparent`)

## Support

Report issues at: https://github.com/ricslash/HAamazonparent/issues
