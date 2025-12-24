# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in filtarr, please report it responsibly.

### How to Report

1. **Do NOT open a public GitHub issue** for security vulnerabilities
2. Use [GitHub Security Advisories](https://github.com/dabigc/filtarr/security/advisories/new) to report privately
3. Or email the maintainer directly (see GitHub profile)

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Fix timeline**: Depends on severity
  - Critical: Within 24-48 hours
  - High: Within 7 days
  - Medium: Within 30 days
  - Low: Next scheduled release

### Security Best Practices for Users

1. **API Keys**: Never commit API keys. Use environment variables or config files outside the repo.
2. **Docker**: Run containers with minimal privileges.
3. **Network**: Use HTTPS for Radarr/Sonarr connections when possible.
4. **Updates**: Keep filtarr and dependencies updated.

## Security Features

- All API keys are passed via headers, never in URLs
- No secrets are logged
- Input validation via Pydantic models
- Async HTTP client with proper timeout handling
