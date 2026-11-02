# Loop state — Miao

Updated: 2026-11-01 (loop bootstrap). Facts here are the standing state;
when one changes, the PR that changes it updates this file.

## Direction channel

- Tasks: GitHub Issues labeled `jarvis-task` in this repo.
- Reviews and verdicts: PR comments only.
- Merge owner: Jarvis. External Claude opens PRs from `claude/*` branches.

## Decisions in force

- An off-site backup mirror of this repo exists (executed 2026-10-27);
  restore procedure is documented in the ops runbook held by Jarvis.
- Bilingual editions are a publish gate, not a nice-to-have.

## Acceptance rules

- CI green on the current head; gitleaks is a required strict check.
