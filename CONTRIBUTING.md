# Contributing to Tsuzi

Thank you for your interest in contributing! This document covers the basics.
For the full coding, testing, and git rules, see the canonical docs under
[`docs/standards/`](docs/standards/).

## Quick Start

1. **Fork & clone** the repository.
2. **Create a branch** following the naming convention in
   [`docs/standards/git.md`](docs/standards/git.md):
   ```
   feat/short-description
   fix/short-description
   docs/short-description
   ```
3. **Set up the environment** (Windows 11, Python 3.12):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```
4. **Make your change** following [`docs/standards/coding.md`](docs/standards/coding.md).
5. **Add or update tests** per [`docs/standards/testing.md`](docs/standards/testing.md) — anything with desktop, network, or credential side effects must carry the `side_effect` / `requires_*` markers.
6. **Run the safe smoke gate** and ensure it passes:
   ```powershell
   python -m pytest --collect-only -q --no-test-report
   python -m pytest -q -m safe_smoke --no-test-report
   ```
7. **Open a Pull Request** using the PR template.

## Pull Request Checklist

- [ ] Branch follows the naming convention (`feat/`, `fix/`, `docs/`, etc.)
- [ ] Commit messages follow the format in [`docs/standards/git.md`](docs/standards/git.md)
- [ ] Safe smoke suite passes (`python -m pytest -q -m safe_smoke --no-test-report`)
- [ ] New code is covered by tests where feasible
- [ ] No secrets, `.env` files, or build artifacts committed
- [ ] PR description explains what changed, why, and how it was verified

## Reporting Bugs

Use the GitHub Issue Tracker with the Bug Report template. Include:

- Steps to reproduce
- Expected vs. actual behavior
- Environment details (Windows version, Python version, Ollama model, and whether NVIDIA vision was active)

## Suggesting Features

Use the GitHub Issue Tracker with the Feature Request template. Describe:

- The problem you're trying to solve
- The proposed solution
- Any alternatives you've considered

## Code of Conduct

By participating you agree to abide by the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Questions?

Check the [`docs/`](docs/) knowledge base first. If your question isn't
answered there, open a GitHub issue labeled `question`.
