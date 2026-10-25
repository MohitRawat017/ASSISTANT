# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, use GitHub's private vulnerability reporting: open the repository on
GitHub, go to the **Security** tab, and choose **Report a vulnerability**.
Alternatively, send a private GitHub message to [@MohitRawat017](https://github.com/MohitRawat017).

Include:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Any suggested fixes (optional)

This is a personal project, so there is no formal SLA — reports are answered
as soon as possible. If the vulnerability is confirmed, a fix will be worked
on and disclosure coordinated with you.

## Scope Notes

This assistant runs on the owner's machine with access to:

- `.env` credentials (Gmail app password, Telegram bot token, NVIDIA API key)
- Google account actions (mail, calendar, tasks)
- Desktop control (mouse, keyboard, windows)

Reports involving credential leakage, unsafe automation, or command injection
into tool calls are especially relevant.

If a key was ever pasted into chat, logs, or a trace file, **rotate it** before
reporting — exposed keys are assumed compromised.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (development) | Yes |

## Disclosure Policy

- We follow coordinated disclosure.
- Reporters are credited in release notes unless they prefer to remain
  anonymous.
