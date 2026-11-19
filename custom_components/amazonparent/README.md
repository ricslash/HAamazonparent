# Amazon Parent Dashboard - Home Assistant Integration

**Status**: Phase 2 Complete - Basic Integration Ready for Testing
**Version**: 0.1.0

Home Assistant custom integration for Amazon Parent Dashboard that provides monitoring and control of supervised children's devices (Fire tablets, Echo devices).

## Features

### ✅ Implemented (Phase 2 - v0.1.0)

**Sensors:**
- Daily time limit (in minutes)
- Device count per child
- Curfew information (start/end times)
- Reading goal tracking

**Switches:**
- Pause/resume time limits (1 hour default)

**Buttons:**
- Quick pause: 15 minutes
- Quick pause: 30 minutes
- Quick pause: 1 hour

### 🚧 Planned (Future Phases)

- Binary sensors (bedtime active, limits reached)
- Time limit modification services
- Schedule update services
- App blocking controls
- Real-time usage tracking

## Prerequisites

1. **Amazon Parent Dashboard Auth Add-on** (Phase 1)
   - Must be installed and running
   - Must have completed authentication
   - Default URL: `http://localhost:8100`

2. **Home Assistant**
   - Version 2023.1 or newer
   - Python 3.11+

## Installation

### Method 1: Manual Installation

1. Copy the `custom_components/amazonparent` folder to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/amazonparent/
   ```

2. Restart Home Assistant

3. Add the integration:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "Amazon Parent Dashboard"
   - Enter add-on URL (default: `http://localhost:8100`)

### Method 2: HACS (Custom Repository)

1. Open **HACS** → **Integrations** → **⋮** → **Custom repositories**
2. Add `https://github.com/ricslash/HAamazonparent` with category **Integration**
3. Download **Amazon Parent Dashboard** and restart Home Assistant

## Configuration

The integration uses the authentication add-on for cookie management. No manual configuration of cookies is required.

**Configuration Flow:**
1. Ensure authentication add-on is running
2. Complete authentication via add-on web UI
3. Add integration in Home Assistant
4. Integration automatically fetches cookies from add-on

## Entities Created

For each child in your Amazon household (under device `{Child}'s Account`), the integration creates:

### Sensors
- `sensor.{child}_s_account_daily_time_limit` - Daily time limit in minutes
- `sensor.{child}_s_account_device_count` - Number of devices
- `sensor.{child}_s_account_screen_time_today` - Screen time used today
- `sensor.{child}_s_account_screen_time_this_week` - Screen time used this week
- `sensor.{child}_s_account_screen_time_remaining` - Daily screen time remaining
- `sensor.{child}_s_account_bonus_time` - Bonus minutes granted today (reset at local midnight; adjusted on early clear)
- `sensor.{child}_s_account_bonus_time_remaining` - Remaining minutes on active bonus window

### Switches
- `switch.{child}_s_account_pause_limits` - Pause/resume time limits
- `switch.{child}_s_account_time_limits` - Enable/disable daily time limits

### Buttons
- `button.{child}_s_account_pause_15min` - Pause for 15 minutes
- `button.{child}_s_account_pause_30min` - Pause for 30 minutes
- `button.{child}_s_account_pause_1_hour` - Pause for 1 hour
- `button.{child}_s_account_clear_bonus_time` - Clear active bonus time and restore baseline schedule

### Services
- `amazonparent.add_bonus_time` (`child`, `minutes`) - Grant additive bonus minutes while preserving baseline schedules/limits; `minutes: 0` clears active bonus time
- `amazonparent.clear_bonus_time` (`child`) - Clear active bonus time and restore baseline schedules/limits

## Usage Examples

### Automation: Pause Limits When Homework is Done

```yaml
automation:
  - alias: "Pause Nora's limits after homework"
    trigger:
      - platform: state
        entity_id: input_boolean.nora_homework_complete
        to: "on"
    action:
      - service: button.press
        target:
          entity_id: button.nora_pause_30min
```

### Script: Resume All Limits

```yaml
script:
  resume_all_limits:
    sequence:
      - service: switch.turn_off
        target:
          entity_id:
            - switch.nora_pause_limits
            - switch.rowan_pause_limits
```

## API Integration

This integration communicates with Amazon Parent Dashboard API endpoints:

- `GET /get-household` - Fetch family members
- `GET /get-child-devices` - Fetch devices
- `GET /get-adjusted-time-limits` - Fetch schedules
- `GET /get-bonus-time` - Fetch active bonus-time allotment
- `PUT /set-bonus-time` - Grant additive bonus time
- `PUT /delete-bonus-time` - Clear active bonus time
- `POST /set-offscreen-time` - Pause/resume limits

Authentication is handled via cookies + CSRF tokens extracted by the authentication add-on.

## Troubleshooting

### Integration won't load

1. Check add-on is running: `http://localhost:8100/api/health`
2. Verify cookies exist: `http://localhost:8100/api/cookies/check`
3. Check Home Assistant logs for errors

### Entities not updating

- Integration polls every 60 seconds
- Force update: Reload integration in UI
- Check API connectivity in logs

### Commands not working

- Verify CSRF token is present in cookies
- Re-authenticate via add-on if needed
- Check Amazon account permissions

## Development

### File Structure

```
custom_components/amazonparent/
├── __init__.py              # Integration setup
├── manifest.json            # Integration metadata
├── const.py                 # Constants
├── models.py                # Data models
├── coordinator.py           # Data fetching coordinator
├── config_flow.py           # Configuration UI
├── strings.json             # UI text
├── services.yaml            # Service definitions
├── sensor.py                # Sensor entities
├── switch.py                # Switch entities
├── button.py                # Button entities
└── client/
    ├── __init__.py
    └── api.py              # API client
```

### Testing

The integration has been tested with:
- ✅ Authentication via add-on
- ✅ Cookie retrieval and CSRF token extraction
- ✅ Household and device data fetching
- ✅ Pause/resume limit functionality

## Known Limitations

1. **Child-centric control**: API controls all child's devices together (not per-device)
2. **Polling only**: No real-time push updates (60-second refresh)
3. **Amazon API**: Uses unofficial/reverse-engineered endpoints
4. **TOS concerns**: May violate Amazon Terms of Service

## Support

- **Issues**: https://github.com/ricslash/HAamazonparent/issues
- **Discussions**: https://github.com/ricslash/HAamazonparent/discussions

## License

MIT License

## Disclaimer

⚠️ **Important**: This integration uses unofficial, reverse-engineered Amazon API endpoints. Use at your own risk. This may violate Amazon's Terms of Service and could result in account restrictions.

---

**Phase 2 Complete** ✅
Basic monitoring and control functionality implemented and ready for testing.
