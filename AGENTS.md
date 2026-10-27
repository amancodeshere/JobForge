# JobForge Codex workflow

## Cost routing

- Default to GPT-5.6 Terra. Use low reasoning for narrow, mechanical work and
  medium reasoning for normal implementation, debugging, and review.
- Use GPT-5.6 Sol at medium reasoning only for authentication or authorization,
  privacy/security review, irreversible database migrations, or after the same
  issue has failed two Terra attempts. State the reason for escalation.
- Do not enable Fast mode unless the user explicitly prioritizes speed over
  Codex allowance.
- Do not spawn agents merely to parallelize reading or simple edits. A spawned
  agent repeats context and can cost more than it saves. Use at most one
  subagent, only for an independent, bounded task.
- Keep each Codex task to one roadmap phase or one bug. Start a fresh task once
  its acceptance criteria pass instead of carrying unnecessary context forward.

## Git workflow

- Begin by checking `git status --short`, current branch, and the latest commit.
  Preserve unrelated user changes.
- Use a `feat/<short-scope>` branch for a distinct feature or policy change.
  Keep the branch scoped to one coherent outcome.
- Before committing, run the smallest relevant tests first; run the full suite
  and deployment checks at a phase boundary or before production deployment.
- Commit after every completed, verified phase. Each commit must contain one
  logical change and use an imperative message, for example:
  `feat: persist user search history` or `fix: isolate saved jobs by owner`.
- Do not bundle generated artifacts, credentials, local secrets, or incidental
  formatting changes into feature commits. Review `git diff --check` and
  `git status --short` before staging.
- Push only after tests pass and the commit is inspectable. Do not force-push or
  rewrite shared history without explicit user approval.

## Completion report

- Report the branch, commit hash, changed files, validation commands, and any
  remaining deployment action.
