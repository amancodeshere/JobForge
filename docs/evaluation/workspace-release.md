# Guided workspace release checks

The release separates the public landing/demo from the authenticated workspace.
Native Streamlit navigation uses automatic initial sidebar state: narrow screens
start with a closed drawer, and desktop screens retain the account rail. Long
candidate names and provider job titles wrap within their available width.

## Validation

- `python -m pytest -q` covers identity isolation, CV validation, the private
  workspace gate, the CV-to-preferences-to-results transition, preference
  retention, filters/sorting, and the existing search/application regressions.
- `python main.py validate` checks the demonstration payload.
- `python main.py doctor` checks deployment assets and provider configuration.
- Browser checks resize the landing, demo and workspace through 320, 390, 640,
  768, 980, 1024, 1440 and 2560 CSS pixels. Workspace results are also checked
  with the account rail open using a temporary sample-only harness, outside the
  repository. Tests inspect horizontal overflow inside titles and result rows,
  as well as the document viewport, and stress-test long unbroken names/titles.
- The hosted service must pass `/_stcore/health`, public page navigation and the
  unauthenticated workspace gate after deployment.

These are Chromium viewport checks, not claims of physical-device or full
cross-browser certification. No real applications are submitted by the checks.

## Production sign-in gate

The production Railway service is `JobForge` in project `Job Forge`, environment
`production`, and deploys the repository's `main` branch. Its public domain is
`jobforge-prod.up.railway.app`. At release preparation, no OIDC settings were
configured in the service or local Streamlit secrets. The user requested that
an existing provider be connected. Provider selection/configuration and the
registered callback URL are required before promoting the login-gated workspace;
never enable local personal mode on the hosted service to work around this.
