# Miao

Home of the published Muse skill packages and brand assets for Miao /
vertciti (public). Branch protection is on: PR required, gitleaks check
required and strict.

## How work happens here

- Direction arrives in-repo: GitHub Issues labeled `jarvis-task`, PR
  review comments, and `CLAUDE.md` / `LOOP.md`. Read both at session start.
- External Claude works on `claude/*` branches and opens PRs; it never
  merges its own PRs. Jarvis reviews and merges.
- Review verdicts exist only as PR comments.

## Working rules

- Skills ship bilingual: an English main edition plus a full Chinese
  edition of equal standing (SKILL.md / SKILL.zh.md, README.md /
  README.zh.md). A publish with either edition missing or out of sync
  does not ship.
- Never commit secrets; run the gitleaks check before pushing (it is a
  required status check here).
- Conventional commits; author identity is the Claude noreply identity.
