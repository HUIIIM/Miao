# Experiments

One directory per experiment, `YYYY-MM-DD-slug/`. Copy [`_template/`](_template/) to start.
[`scripts/check_entry.py`](../scripts/check_entry.py) enforces the rules below on every PR, and the PR
cannot pass while an entry breaks them.

| File | What it is |
|---|---|
| `README.md` | At least one paragraph: what was tried, why, and what happened. Failed runs count. |
| `run.sh`, `run.py` or a `.ipynb` | The runnable minimal loop. |
| `output/` | The real output, unedited. Never ignored by `.gitignore`. |
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

The first seven fields are required. `status` is `works`, `failed` or `superseded`. A superseded entry needs
`superseded_by`, and a run that went over `max_cost_usd` cannot be marked `works`.

## Never commit

The repository and its history are public and permanent.

- API keys, tokens, cookies or `.env` files. Gitleaks scans every PR, but by then the secret is already public.
- Personal data about anyone, including you: messages, contacts, calendars, health, location.
  Use synthetic or redacted inputs, and say so in the entry's README.
- Output you have no right to publish, such as third-party content or data under a restrictive licence.

The licence for prose and data in this directory has not been decided yet. The code is MIT (see `LICENSE`).
