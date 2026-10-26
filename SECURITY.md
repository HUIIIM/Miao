# Security Policy

## Reporting a vulnerability

Do not open a public issue. Use **Report a vulnerability** under this repository's **Security** tab; the report
stays private between you and the maintainer. If private reporting is unavailable, use the contact links on
[vertciti.com](https://vertciti.com).

Expect a first response within 48 hours.

## Secrets

This repository is public. Never commit API keys, tokens or `.env` files. Every push and pull request is scanned
with gitleaks (`.github/workflows/gitleaks.yml`); if a secret does land, rotate it first, then remove it from history.
