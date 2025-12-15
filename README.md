# Amazon Parent Dashboard for Home Assistant

**Version**: 0.1.0
**Status**: Phase 2 Complete - Ready for Testing

A complete Home Assistant solution for monitoring and controlling Amazon Parent Dashboard supervised devices (Fire tablets, Echo devices, Kindle devices).

## Overview

This project provides two components that work together:

1. **Authentication Add-on** (`addon/`) - Browser-based authentication service using Playwright and VNC
2. **Custom Integration** (`custom_components/amazonparent/`) - Home Assistant integration for device control and monitoring

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

## Installation

### Prerequisites

- Home Assistant 2023.1 or newer
- Python 3.11+
- Supervisor access (for add-on installation)

### Step 1: Install Authentication Add-on

1. Copy the `addon/` folder to `/addons/amazonparent-playwright-ha/` in your Home Assistant configuration directory

2. Reload the add-on store:
   - Go to **Supervisor** → **Add-on Store** → **⋮** → **Reload**

3. Install the add-on:
   - Find "Amazon Parent Dashboard Auth" in the local add-ons list
   - Click **Install**
   - Start the add-on

4. Authenticate with Amazon:
   - Click "Open Web UI" or navigate to `http://[YOUR_HA_IP]:8100`
   - Click "Start Authentication"
   - Connect via VNC to see the browser: `vnc://[YOUR_HA_IP]:5903`
     - Password: `amazonparent`
   - Sign in to your Amazon account in the VNC browser
   - Wait for success message

### Step 2: Install Custom Integration

1. Copy the `custom_components/amazonparent/` folder to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/amazonparent/
   ```

2. Restart Home Assistant

3. Add the integration:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "Amazon Parent Dashboard"
   - Enter add-on URL (default: `http://localhost:8100`)

## Configuration

The integration uses the authentication add-on for cookie management. No manual configuration of cookies is required.

### Add-on Configuration Options

- **log_level**: Set logging level (trace, debug, info, warning, error)
- **auth_timeout**: Timeout for authentication in seconds (60-600)
- **session_duration**: How long cookies remain valid (3600-604800 seconds)

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

## Architecture

### Authentication Flow

1. Add-on runs Playwright in headless browser
2. User authenticates via VNC-accessible browser
3. Add-on extracts cookies and CSRF tokens
4. Integration retrieves cookies from add-on API
5. Integration uses cookies for Amazon API calls

### API Endpoints

The integration communicates with Amazon Parent Dashboard API endpoints:

- `GET /get-household` - Fetch family members
- `GET /get-child-devices` - Fetch devices per child
- `GET /get-adjusted-time-limits` - Fetch schedules and limits
- `POST /set-offscreen-time` - Pause/resume time limits

### Add-on API Endpoints

The authentication add-on provides:

- `GET /api/health` - Health check
- `GET /api/cookies/check` - Verify cookies exist
- `GET /api/cookies` - Retrieve stored cookies
- `POST /auth/start` - Start authentication process

## Troubleshooting

### Integration won't load

1. Verify add-on is running: `http://localhost:8100/api/health`
2. Check cookies exist: `http://localhost:8100/api/cookies/check`
3. Review Home Assistant logs for errors
4. Restart both add-on and Home Assistant

### Authentication fails

1. Ensure VNC connection works: `vnc://[YOUR_HA_IP]:5903`
2. Check add-on logs for errors
3. Try increasing `auth_timeout` in add-on configuration
4. Verify Amazon credentials are correct

### Entities not updating

- Integration polls every 60 seconds
- Force update: Reload integration in UI
- Check network connectivity to Amazon
- Verify cookies haven't expired

### Commands not working

- Verify CSRF token is present in cookies
- Re-authenticate via add-on if needed
- Check Amazon account has proper parental control permissions
- Review integration logs for API errors

## Project Structure

```
HAamazonparent/
├── README.md                          # This file
├── addon/                             # Authentication Add-on
│   ├── config.json                    # Add-on configuration
│   ├── Dockerfile                     # Container definition
│   ├── README.md                      # Add-on documentation
│   ├── requirements.txt               # Python dependencies
│   ├── app/                           # Application code
│   └── rootfs/                        # Container filesystem
└── custom_components/amazonparent/    # Home Assistant Integration
    ├── __init__.py                    # Integration setup
    ├── manifest.json                  # Integration metadata
    ├── config_flow.py                 # Configuration UI
    ├── coordinator.py                 # Data update coordinator
    ├── const.py                       # Constants
    ├── models.py                      # Data models
    ├── sensor.py                      # Sensor entities
    ├── switch.py                      # Switch entities
    ├── button.py                      # Button entities
    ├── strings.json                   # UI translations
    ├── client/                        # API client
    │   └── api.py                     # Amazon API wrapper
    └── translations/                  # Localization files
```

## Known Limitations

1. **Child-centric control**: API controls all of a child's devices together (not per-device)
2. **Polling only**: No real-time push updates (60-second refresh interval)
3. **Unofficial API**: Uses reverse-engineered Amazon endpoints
4. **Browser authentication**: Requires manual login via VNC for initial setup
5. **Session expiry**: Cookies may expire; requires re-authentication

## Development

### Testing

The integration has been tested with:
- Authentication via Playwright add-on
- Cookie retrieval and CSRF token extraction
- Household and device data fetching
- Pause/resume limit functionality
- Multi-child household support

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Security Considerations

This integration is designed for home use on **trusted local networks**:

- 🏠 **Local Network Only**: Runs on your local network (not internet-exposed)
- 🔐 **Encrypted Storage**: Amazon session cookies are encrypted before storage
- 👁️ **VNC Access**: VNC password (`amazonparent`) allows viewing the browser during authentication
- 🔒 **Isolated Container**: Add-on runs in isolated Docker container
- ⚠️ **No Internet Exposure**: Do NOT expose Home Assistant directly to the internet
- ✅ **Remote Access**: Use a VPN (WireGuard, Tailscale) for remote access instead of port forwarding

**Important**: No credentials are stored permanently (session cookies only).

For detailed security information, see [SECURITY.md](SECURITY.md).

## Roadmap

### Future Enhancements

- Binary sensors (bedtime active, limits reached, device online status)
- Time limit modification services
- Schedule update services
- App blocking controls
- Real-time usage tracking
- HACS integration
- Multi-language support

## Support

- **Issues**: https://github.com/ricslash/HAamazonparent/issues
- **Discussions**: https://github.com/ricslash/HAamazonparent/discussions
- **Documentation**: https://github.com/ricslash/HAamazonparent

## License

MIT License

## Disclaimer

**Important**: This integration uses unofficial, reverse-engineered Amazon API endpoints. Use at your own risk. This may violate Amazon's Terms of Service and could result in account restrictions. The authors are not responsible for any issues arising from the use of this integration.

This project is not affiliated with, endorsed by, or sponsored by Amazon.com, Inc. or its affiliates.

---

**Made with Home Assistant** | Phase 2 Complete
