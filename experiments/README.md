# Experiments

One directory per experiment, `YYYY-MM-DD-slug/`. Copy [`_template/`](_template/) to start.
[`scripts/check_entry.py`](../scripts/check_entry.py) enforces the rules below. The `Checks` workflow runs it on every
PR and fails when an entry breaks them. It blocks a merge only if `Checks` is a required status check in the
branch protection settings, which the owner sets.

| File | What it is |
|---|---|
| `README.md` | At least one paragraph: what was tried, why, and what happened. Failed runs count. The template's placeholder is rejected. |
| `run.sh`, `run.py` or a `.ipynb` | The runnable minimal loop. The template's stub is rejected. |
| `output/` | The real output, unedited: at least one non-empty file. `.gitkeep` and empty files do not count, and no file may be a symbolic link. |
| `run.json` | The run manifest: command, start time, duration, environment, status and the sha256 of every output file. |

After a run, record the output hashes with:

```bash
python3 scripts/check_entry.py --write-manifest experiments/2026-11-01-my-test
```

## run.json

```json
{
  "schema_version": 1,
  "command": "python3 run.py > output/stdout.txt",
  "started_at": "2026-11-01T10:00:00Z",
  "duration_s": 12.4,
  "environment": {"python": "3.12.3", "os": "ubuntu-24.04"},
  "status": "works",
  "outputs": {"output/stdout.txt": "<sha256>"},
  "code_commit": "<commit the run used>",
  "model": "<full model version id, never an alias>",
  "seed": 0,
  "tokens": {"input": 0, "output": 0},
  "cost_usd": 0.0,
  "max_cost_usd": 1.0
}
```

The first seven fields are required. `started_at` must be an ISO-8601 date-time with a timezone, `duration_s`,
`cost_usd` and `max_cost_usd` must be finite numbers, and `model` must be a versioned id, not an alias such as
`latest`. `status` is `works`, `failed` or `superseded`. A superseded entry needs `superseded_by`, and a run
that went over `max_cost_usd` cannot be marked `works`.

## Never commit

The repository and its history are public and permanent.

- API keys, tokens, cookies or `.env` files. Gitleaks scans every PR, but by then the secret is already public.
- Personal data about anyone, including you: messages, contacts, calendars, health, location.
  Use synthetic or redacted inputs, and say so in the entry's README.
- Output you have no right to publish, such as third-party content or data under a restrictive licence.

The licence for prose and data in this directory has not been decided yet. The code is MIT (see `LICENSE`).
