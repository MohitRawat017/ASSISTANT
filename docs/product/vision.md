# Product Vision

**Question this document answers:** Why does this product exist?

Does not cover what's being built next — see [roadmap.md](./roadmap.md).
Does not cover system design — see [../architecture/overview.md](../architecture/overview.md).

## Problem Statement

A power user's day is spread across chat windows, mail, calendars, task
lists, and the desktop itself. Cloud assistants can chat but cannot reliably
operate your PC, and they send your screen, mail, and keystrokes to someone
else's servers. The cost is either doing the work manually or giving up
privacy.

## Solution Statement

Tsuzi solves this by running the whole assistant on the owner's Windows
machine: a LangGraph agent that actually calls tools — apps, windows,
mouse/keyboard, Gmail, Calendar, Tasks, Telegram — with long-term memory and
optional screen vision, defaulting to local Ollama models. Unlike cloud
assistants, the default path keeps data on-device; unlike scripted
automation, it understands natural language and decides the steps itself.

## Target Users

| Persona | Primary Need |
|---------|--------------|
| Owner-operator (single user) | One private assistant that controls the desktop and handles productivity without a cloud middleman |

## Success Criteria

How we know the vision is being realized — outcomes, not features.

- Core runtime (chat, tools, memory) works with zero cloud keys
- Everyday commands — open apps, set reminders, manage tasks, send mail — succeed without retries
- The assistant is reachable and controllable remotely via Telegram
- Any failed query is explainable from the JSONL trace

## Explicit Non-Goals

- Multi-user hosted service or SaaS
- macOS/Linux desktop control
- Model training or fine-tuning
- A full GUI launcher — terminal and Telegram are the interfaces

## Related Documents

- What's being built to realize this vision: [roadmap.md](./roadmap.md)
- How the system is structured to deliver it: [../architecture/overview.md](../architecture/overview.md)
