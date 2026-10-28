# Runbook

This repository holds no service, only git history, so the runbook covers one asset: the history itself.
Losing it loses the evidence that experiments rest on.

## Backup

| Copy | Where | How often | Protects against |
|---|---|---|---|
| 1 | github.com/HUIIIM/Miao | every push | — (primary) |
| 2 | Actions artifact `miao-bundle-<run id>` from [`backup.yml`](../.github/workflows/backup.yml), kept 90 days | weekly (Sunday 03:00 UTC) and on demand | force-push, branch deletion, bad merge |
| 3 | **Off-GitHub**: the owner's Google Drive backup set, 「JARVIS 系统备份」 → `<snapshot>/L2-工程层/HUIIIM-Miao-mirror-<date>.bundle` | refreshed with the owner's weekly backup increment | losing the GitHub account or organisation |

Copy 3 is kept by the owner outside GitHub. The first copy is
`2026-10-27-incremental/L2-工程层/HUIIIM-Miao-mirror-2026-10-27.bundle`: a `git bundle --all` of a fresh
`git clone --mirror`, 36,426 bytes, SHA-256 `1e353169b240ca2d6babc612cb38efc6d2e22a5f4332f09bac3e3100317d00c0`.
The owner reported its verification on PR #6 (see the drill log). The fixity list
`fixity-manifest-2026-10-27-incremental-L2L3.sha256` is kept in the same snapshot folder. To check a downloaded
copy, compare its SHA-256 with that value, then follow **Restore** below.

A bundle must be made from a **mirror** clone. A bundle of an ordinary clone stores other branches as
`refs/remotes/origin/*`, which `git clone` does not restore. A bundle of a clone that has not fetched records
stale heads. Both problems came up in drills (see the log below).

```bash
git clone --mirror https://github.com/HUIIIM/Miao.git miao.git
git -C miao.git bundle create ../miao-$(date +%F).bundle --all
git -C miao.git bundle verify ../miao-$(date +%F).bundle      # must print "... is okay"
sha256sum miao-$(date +%F).bundle
```

The weekly workflow does the same, then restores the bundle in a fresh directory and fails if any branch or tag
differs. Every run is therefore also a restore drill, and its artifact carries `restore-drill.txt`.

## Restore

```bash
sha256sum -c miao.bundle.sha256                                  # the bundle is the one that was backed up
git clone --mirror miao.bundle Miao-restored.git                 # restores every branch and tag
git -C Miao-restored.git bundle verify ../miao.bundle            # must print "... is okay"
git -C Miao-restored.git fsck --full                             # must print nothing
git -C Miao-restored.git for-each-ref 'refs/heads/' 'refs/tags/' # compare with miao.bundle.heads
```

To put the history back on a host, push branches and tags only. Do not use `push --mirror`: it deletes refs
that exist on the host but not in the backup, and GitHub rejects its read-only `refs/pull/*` refs.

```bash
git -C Miao-restored.git push https://github.com/HUIIIM/Miao.git 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'
```

Targets: RPO is one week for copy 2 and one month for copy 3. RTO is under 15 minutes, which is the time to
download one bundle and run the blocks above.

## Drill log

Do a timed restore at least once a quarter, and record each drill here.

| Date | Who | Source | Result | Time | Notes |
|---|---|---|---|---|---|
| 2026-10-27 | author session (wrote PR #6), sandbox | `git bundle --all` of an unfetched local clone at `16a9465` | ok, but flawed: verify ok, fsck clean, 11 commits | 0.13 s (10.9 KB) | The local `main` ref was stale (`5c88515`). The independent assessor then showed that restoring with `git clone` loses non-`main` branches. Both are fixed by the mirror procedure above. Not off-site. |
| 2026-10-27 | owner (reported on PR #6) | off-site copy 3, downloaded back from Google Drive | ok: Drive md5 and downloaded SHA-256 match the source; `bundle verify` ok; restored `main` = `16a9465`, `claude/sota-roadmap-fixes` = `6e03954`, level with GitHub; no tags; fsck clean | not recorded | First off-site copy. Reported by the owner, not re-checked by this session, which has no access to the Drive. |
| 2026-10-28 | author session (wrote PR #6), sandbox | mirror of github.com/HUIIIM/Miao (6 refs incl. `refs/pull/*`), bundle 23.9 KB | ok: restored refs = bundle heads = GitHub refs; `fsck --full` empty; the branches-and-tags push below rebuilt both branches on a new bare host | backup 0.81 s, restore and push 0.11 s | Not off-site. Not an independent drill: the assessor or owner should repeat it on a downloaded artifact. |

## Leaked secret

1. Rotate the secret at its provider first. The repository is public, so assume it was copied.
2. Remove it from history only after rotating it, then record what happened in this file.
3. Check that the next `gitleaks` run is green.
