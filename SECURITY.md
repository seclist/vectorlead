# 🔒 Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2.0 | :x:                |

---

## Reporting a Vulnerability

The VectorLead team takes security, user privacy, and responsible scraping boundaries seriously.

If you believe you have found a security vulnerability in VectorLead (including credential leakage, denial-of-service, or remote execution risks):

1. **Do not create a public GitHub issue.**
2. Send an email to **security@vectorlead.dev** (or open a private security advisory on GitHub under the **Security** tab).
3. Include:
   - Description of the issue
   - Minimal reproduction script or CLI commands
   - Potential impact
4. We will acknowledge receipt within 48 hours and work with you on a patch prior to public disclosure.

---

## Ethical & Non-Invasive Crawler Guidelines

VectorLead is designed around **zero-login, read-only crawler headers** (`facebookexternalhit/1.1`) to inspect publicly accessible OpenGraph meta tags.

VectorLead does **not**:
- Bypass two-factor authentication or private account security boundaries.
- Automate unauthorized direct messages or comment spam.
- Require or store user session cookies or passwords.

Users are responsible for ensuring their outreach practices comply with applicable local laws (e.g., CAN-SPAM, GDPR) and platform terms of service.
