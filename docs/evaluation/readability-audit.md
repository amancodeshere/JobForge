# Readability audit

This fix addresses the dark text on green employment/experience tags and the
primary search action. A global descendant color reset overrode native control
foregrounds, and the form-submit variant was missing from primary-button styles.
Removing that reset and covering both native primary variants restores white
labels and remove icons on eucalyptus controls.

Additional verified corrections:

- Captions use an opaque foreground instead of combining a muted color with
  Streamlit’s 0.6 opacity. This improves supporting guidance and account-rail copy.
- Disabled actions use readable slate text on a subdued paper surface, rather
  than fading the whole control. They remain disabled.
- Success, warning and error messages use the existing darker semantic tokens.
- Hover text inherits the foreground of its filled button; keyboard focus stays
  visible with a 3px outline.

## Rendered checks

The real preferences function and native controls were rendered in an isolated
sample-only Streamlit harness, without changing a user’s CV, preferences or
search results. Chromium computed-style checks included effective foreground,
background and opacity; positioned slider labels were measured against the
workspace behind them rather than a thumb outside their text bounds.

| Text/state | Measured contrast |
| --- | ---: |
| Selected tags and primary search/action/download labels | 5.96:1 |
| Primary search hover | 8.17:1 |
| Supporting captions | 5.91:1 |
| Account-rail captions | 8.84:1 |
| Disabled action | 7.12:1 |
| Secondary-action hover | 11.66:1 |

All 37 checked visible text samples in the representative preferences/status
fixture met 4.5:1 for normal text or 3:1 for large text. Hover checks had no
contrast failures. Placeholder text uses the same readable muted foreground.
The landing page (32 samples) and demonstration results (88 samples) also
had no measured contrast failures. Screenshots were inspected on desktop and mobile. Dynamic viewport checks at
320, 390, 768, 1024, 1440 and 2560 CSS pixels found no page-level overflow.

Validation commands: `python -m pytest -q`, `python main.py validate`,
`python main.py doctor`, and `git diff --check`. The 120-test suite passed.
The design detector reported advisory token/type drift, with no blocking
findings. These checks target readability; they are not a claim of complete
WCAG certification or physical-device/cross-browser coverage.
