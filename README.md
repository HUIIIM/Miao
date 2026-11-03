# Miao

苗家辉（Jiahui Miao）的公开实验室：a personal lab repository for small experiments, notes and scratch work
from building a personal AI. It is not a product.

| | |
|---|---|
| Status | lab — personal experiments; no experiment has been committed yet (the repository holds the entry rules, a checker, a template and CI) |
| Type | personal lab repository |
| Licence | MIT ([LICENSE](LICENSE)), Copyright (c) 2026 Jiahui Miao |
| Languages | English; Chinese name only (苗家辉) |
| Contact | Profile: [@HUIIIM](https://github.com/HUIIIM) · Build logs: [vertciti.com](https://vertciti.com) |

## Overview

This repository is a lab notebook. It is meant for tiny prototypes, one-off scripts and notes that are not
ready for a product repository. Nothing here is a product or a commitment; when an experiment grows into
something larger, it moves to its own repository.

The private `miao` personal-AI engine is a separate project and does not live here.

## What an entry needs

An experiment is added only when it has:

- a runnable minimal loop,
- a short paragraph explaining what was tried and why,
- its real output, committed as evidence.

Nothing is added to make the repository look active.

The layout, the `run.json` manifest and what must never be committed are in
[experiments/README.md](experiments/README.md). On every pull request, the `Checks` workflow runs
`scripts/check_entry.py` and fails when an entry breaks the rule.

## Where to start

- [@HUIIIM](https://github.com/HUIIIM) — profile and the list of product repositories
- [vertciti.com](https://vertciti.com) — build logs

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Never commit API keys or `.env` files; every pull request and every push to `main` is scanned for secrets.

## Operations

Backups and restore steps: [docs/RUNBOOK.md](docs/RUNBOOK.md). Besides GitHub, the history is kept as a weekly
bundle artifact and in the owner's own backup set. A weekly workflow also asks the public
[Software Heritage](https://www.softwareheritage.org) archive for a snapshot, and `scripts/offsite_check.py`
verifies it. The archive holds no snapshot of this repository yet; the first is taken when that workflow first
runs on `main`.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Jiahui Miao.

Built by vertciti — https://vertciti.com
