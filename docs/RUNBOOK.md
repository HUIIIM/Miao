# Runbook

This repository holds no service, only git history, so the runbook covers one asset: the history itself.
Losing it loses the evidence that experiments rest on.

## Backup

| Copy | Where | How often | Protects against |
|---|---|---|---|
| 1 | github.com/HUIIIM/Miao | every push | — (primary) |
| 2 | Actions artifact `miao-bundle-<run id>` from [`backup.yml`](../.github/workflows/backup.yml), kept 90 days | weekly (Sunday 03:00 UTC) and on demand | force-push, branch deletion, bad merge |
| 3 | **Off-GitHub**: owner downloads the latest bundle to storage outside GitHub | monthly, owner | losing the GitHub account or organisation |

Copy 3 is a manual step for the owner. Until it has been done at least once, the repository has no off-site
backup, and SOTA OPS-1 stays failed.

To make a bundle by hand, fetch first. A bundle made from a clone that has not fetched records stale
branch heads (found in the 2026-10-27 drill below):

```bash
git clone --mirror https://github.com/HUIIIM/Miao.git miao.git
git -C miao.git bundle create ../miao-$(date +%F).bundle --all
git bundle verify miao-$(date +%F).bundle
sha256sum miao-$(date +%F).bundle
```

## Restore

```bash
git bundle verify miao.bundle                  # must print "... is okay"
git clone miao.bundle Miao-restored
cd Miao-restored && git fsck --full            # must print nothing
git log --oneline -1 origin/main               # compare with miao.bundle.head
git remote set-url origin https://github.com/HUIIIM/Miao.git   # or a new host
git push --mirror origin                       # only when restoring the primary
```

Targets: RPO is one week for copy 2 and one month for copy 3. RTO is under 15 minutes, which is the time to
download one bundle and run the block above.

## Drill log

Do a timed restore at least once a quarter, and record each drill here.

| Date | Who | Source | Result | Time | Notes |
|---|---|---|---|---|---|
| 2026-10-27 | assessor session (sandbox) | `git bundle --all` of a local clone at `16a9465` | ok: `bundle verify` ok, `fsck --full` clean, 11 commits, `origin/main` = `16a9465` | 0.13 s (10.9 KB) | Local `main` ref was stale (`5c88515`), so a bundle of an unfetched clone backs up old heads. Fixed by fetching first. Not off-site. |

## Leaked secret

1. Rotate the secret at its provider first. The repository is public, so assume it was copied.
2. Remove it from history only after rotating it, then record what happened in this file.
3. Check that the next `gitleaks` run is green.
