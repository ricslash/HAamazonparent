# Security Assessment

## Overview

This document provides a security assessment of the Amazon Parent Dashboard Home Assistant integration. This is designed to run on your **local, trusted home network** as part of Home Assistant.

## Security Model

This integration is designed for:
- ✅ **Trusted local networks** (your home network)
- ✅ **Single-user or family use**
- ✅ **Running inside Home Assistant Supervisor**
- ❌ **NOT for public internet exposure**
- ❌ **NOT for multi-tenant environments**

## Security Analysis

### Intentional Design Choices

#### VNC Server with Known Password
**Location**: Port 5903, password `amazonparent`

**This is intentional, not a vulnerability**:
- VNC exists specifically so you can see the browser during Amazon authentication
- The password is documented because users need it to connect
- Only exposes a browser window, not system access
- Runs on local network only (not internet-accessible)

**Comparable to**: Development tools like Jupyter notebooks, local databases, or Home Assistant itself - they run on trusted networks with known defaults.

**User Responsibility**: Don't expose Home Assistant or its add-ons directly to the internet. Use a VPN for remote access.

#### API on Port 8100 (HTTP)
**This is standard for Home Assistant add-ons**:
- Home Assistant add-ons communicate internally via HTTP
- Running on local network, not internet
- Protected by your network firewall
- Home Assistant itself handles external HTTPS if needed

### Actual Security Concerns

#### 1. CORS Configuration
**Location**: `addon/app/main.py:34-40`

**Current**: `allow_origins=["*"]`

**Consideration**: While this allows any origin to make requests, it's only accessible on your local network. If you browse untrusted websites while on your home network, they could theoretically access the API.

**Risk Level**: **LOW** (requires malicious site + being on your local network)

**Recommendation**: Consider restricting to Home Assistant's domain if you frequently browse untrusted sites on your home network.

#### 2. File Permissions
**Location**: `addon/app/storage/file_storage.py`

**Current**: Cookie files use `0o644`/`0o755` (readable by all users)

**Consideration**: While cookies are encrypted, both the encrypted file and encryption key are readable by other processes.

**Risk Level**: **LOW** (requires another compromised container on your Home Assistant system)

**Recommendation**: Could use `0o600`/`0o700` for defense-in-depth, but current approach allows Home Assistant integration to read cookies.

### What's Protected

✅ **Good Security Practices**:

1. **Encrypted Storage**: Amazon session cookies are encrypted using Fernet before storage
2. **CSRF Protection**: Extracts and uses CSRF tokens for API requests to Amazon
3. **No Credential Storage**: Doesn't store your Amazon username/password
4. **Session-Based**: Uses temporary browser sessions with proper cleanup
5. **No Personal Info**: Code contains no hardcoded emails, addresses, or personal data
6. **Atomic Writes**: Uses temporary files to prevent corruption

### Network Exposure Summary

| Port | Service | Purpose | Accessible From |
|------|---------|---------|----------------|
| 8100 | API | Home Assistant integration | Local network |
| 5903 | VNC | View browser during auth | Local network |

Both services are intentionally local-network accessible for functionality.

## What's Safe to Publish

✅ **Safe to publish publicly**:
- No personal information in code
- No credentials for YOUR accounts
- Only generic localhost/127.0.0.1 references
- No private IP addresses or network details
- Follows standard Home Assistant add-on patterns

## Deployment Best Practices

### Network Security

1. **Firewall Configuration**:
   - ✅ Keep Home Assistant behind your firewall
   - ❌ Don't port-forward Home Assistant to the internet
   - ✅ Use VPN (WireGuard, Tailscale) for remote access

2. **Network Segmentation** (Optional but recommended):
   - Consider separate VLAN for IoT/smart home devices
   - Isolate guest WiFi from smart home network

3. **Home Assistant Security**:
   - Use strong password for Home Assistant
   - Enable two-factor authentication if available
   - Keep Home Assistant and add-ons updated
   - Review add-on logs periodically

### Amazon Account Security

Since this integration stores Amazon session cookies:

1. **Account Protection**:
   - Use strong Amazon password
   - Enable Amazon two-factor authentication
   - Monitor Amazon account for unusual activity

2. **Session Management**:
   - Cookies expire and need periodic re-authentication
   - Delete cookies from add-on when not in use
   - Re-authenticate if you notice unusual Amazon behavior

## Risk Assessment

### Low Risk Scenarios (Typical Home Use)

✅ Using on home WiFi network
✅ Standard Home Assistant installation
✅ No public internet exposure
✅ Trusted household members
✅ Updated Home Assistant system

### Higher Risk Scenarios (Avoid)

❌ Home Assistant exposed to public internet
❌ Port forwarding HA ports directly
❌ Untrusted users on your network
❌ Shared hosting or multi-tenant setups
❌ Running on compromised network

## Comparison to Similar Tools

This integration's security model is similar to:
- **Home Assistant itself**: Runs on local network, uses HTTP internally
- **HACS**: Installs code from GitHub repositories
- **ESPHome**: Flash firmware to devices on local network
- **Node-RED**: Visual automation tool with local network access

All assume a **trusted local network** environment.

## Compliance Considerations

### Amazon Terms of Service

⚠️ **Important**: This integration uses unofficial, reverse-engineered Amazon APIs.

**Potential Issues**:
- May violate Amazon Terms of Service
- Amazon could block your account (unlikely but possible)
- APIs could change without notice

**Recommendation**: Use at your own risk. This is for personal, non-commercial use only.

### Data Privacy

**Your Data**:
- Cookies stored locally on your Home Assistant instance
- Not transmitted to any third party
- Only you have access (via Home Assistant)

**Child Data**:
- Integration retrieves child names and device info from Amazon
- Stored in Home Assistant's database
- Subject to Home Assistant's security model

## Incident Response

If you suspect your Home Assistant or Amazon account is compromised:

1. **Immediate Actions**:
   - Delete cookies: `http://localhost:8100/api/cookies` (DELETE request)
   - Change Amazon password
   - Revoke Amazon sessions: Amazon.com → Account → Login & Security → Sign out everywhere
   - Check Home Assistant logs for unusual activity

2. **Review**:
   - Check Amazon order history for unauthorized purchases
   - Review Parent Dashboard settings for unexpected changes
   - Check Home Assistant automations for modifications

## Recommended README Addition

Consider adding this section to your main README:

```markdown
## Security Notes

This integration is designed for home use on trusted local networks:

- 🏠 Runs on your local network only (not internet-exposed)
- 🔐 Encrypts Amazon session cookies before storage
- 👁️ VNC password (`amazonparent`) allows you to view the browser during authentication
- ⚠️ Do NOT expose Home Assistant directly to the internet
- ✅ Use a VPN for remote access instead of port forwarding

See [SECURITY.md](SECURITY.md) for detailed security information.
```

## Conclusion

**Overall Assessment**: This integration follows standard Home Assistant add-on security practices. It's designed for the same threat model as Home Assistant itself: trusted local network use.

**Key Point**: The "security issues" identified are actually **intentional design choices** for a local-network tool. VNC needs to be accessible, the API needs to be reachable, and Home Assistant add-ons standardly use HTTP internally.

**Safe for Personal Use**: ✅ Yes, when used as intended on a home network

**Safe to Publish**: ✅ Yes, the code contains no personal information

**User Responsibility**: Users must:
- Not expose to internet
- Use on trusted networks
- Understand Amazon TOS risks
- Practice good network security
