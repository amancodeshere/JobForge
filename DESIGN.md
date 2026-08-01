---
name: JobForge
description: An editorial opportunity workspace that turns career intent into verified application evidence.
colors:
  mineral-paper: "#f5f6f3"
  mineral-paper-deep: "#e9ece8"
  mineral-white: "#fcfdfb"
  carbon: "#101418"
  slate: "#263b48"
  deep-slate-dossier: "#142936"
  slate-soft: "#38505e"
  steel: "#7f8e94"
  rule: "#c9cfcc"
  rule-dark: "#71868f"
  eucalyptus: "#2b6e66"
  eucalyptus-deep: "#20584f"
  eucalyptus-soft: "#dcebe6"
  warning: "#76501e"
  focus-light: "#76501e"
  focus-dark: "#8fd4c8"
  danger: "#9b3b3b"
typography:
  display:
    fontFamily: '"JobForge Display", "Arial Narrow", sans-serif'
    fontSize: "clamp(4.4rem, 8.2vw, 7.8rem)"
    fontWeight: 600
    lineHeight: 0.77
    letterSpacing: "-0.028em"
  headline:
    fontFamily: '"JobForge Display", "Arial Narrow", sans-serif'
    fontSize: "clamp(2rem, 4vw, 3.4rem)"
    fontWeight: 600
    lineHeight: 0.9
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Avenir Next", Avenir, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "1.08rem"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "normal"
  body:
    fontFamily: '"Avenir Next", Avenir, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.58
    letterSpacing: "normal"
  label:
    fontFamily: '"Avenir Next", Avenir, "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.045em"
rounded:
  square: "0px"
  restrained: "3px"
  circular: "50%"
spacing:
  xs: "0.25rem"
  sm: "0.55rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
  2xl: "2.5rem"
  3xl: "5rem"
components:
  button-primary:
    backgroundColor: "{colors.eucalyptus}"
    textColor: "{colors.mineral-white}"
    rounded: "{rounded.restrained}"
    padding: "0.55rem 0.8rem"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.eucalyptus-deep}"
    textColor: "{colors.mineral-white}"
    rounded: "{rounded.restrained}"
    height: "46px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.slate}"
    rounded: "{rounded.restrained}"
    padding: "0.55rem 0.8rem"
    height: "46px"
  input-dossier:
    backgroundColor: "#1c3442"
    textColor: "#f8faf9"
    rounded: "{rounded.restrained}"
    height: "46px"
  opportunity-row:
    backgroundColor: "transparent"
    textColor: "{colors.carbon}"
    rounded: "{rounded.square}"
    padding: "1rem 0"
  evidence-score:
    backgroundColor: "transparent"
    textColor: "{colors.eucalyptus-deep}"
    typography: "{typography.headline}"
    rounded: "{rounded.circular}"
    width: "3.8rem"
---

# Design System: JobForge

## Overview

**Creative North Star: "The Opportunity Front"**

JobForge is a formal editorial workspace where career language becomes evidence. A mineral-paper field and a deep-slate search dossier create a calm, composed front; monumental condensed role language establishes ambition, then strict horizontal rules resolve that ambition into ranked opportunities, provenance and application proof.

The system is sharp without becoming severe, dynamic without becoming restless, and inclusive from graduate to executive. Its restraint is functional: users should always understand what they asked for, where a recommendation came from, how it was scored and what evidence can support an honest application. Generic recruitment-card dashboards, gamified surfaces and decorative bento grids are explicit anti-references.

**Key Characteristics:**

- Mineral-white workspace anchored by a deep-slate search dossier.
- Monumental condensed headlines paired with a sober workhorse UI sans.
- Ledger rows, strict rules and evidence registers instead of floating cards.
- Controlled eucalyptus signals reserved for verified state and primary action.
- Flat surfaces with limited, state-driven ambient lift.
- One reduced-motion-safe settling sequence for the role-language front.

## Colors

The palette behaves like a printed case file: near-neutral mineral paper, carbon type, cool slate structure and a rare eucalyptus signal that means evidence or action.

### Primary

- **Controlled Eucalyptus** (`colors.eucalyptus`): Primary search actions, live status dots and evidence-positive accents.
- **Deep Eucalyptus** (`colors.eucalyptus-deep`): Evidence text, recommendation labels and the deliberate hover state of primary actions.
- **Soft Eucalyptus Wash** (`colors.eucalyptus-soft`): Selected tags and quiet evidence backgrounds inside the dossier.

### Neutral

- **Mineral Paper** (`colors.mineral-paper`): The default application canvas.
- **Pressed Mineral Paper** (`colors.mineral-paper-deep`): A subtle tonal alternative where separation needs more than a rule.
- **Mineral White** (`colors.mineral-white`): Hover-revealed row surfaces and the lightest content ground.
- **Carbon** (`colors.carbon`): Primary text, major rules and the strongest structural contrast.
- **Deep Slate Dossier** (`colors.deep-slate-dossier`): The search rail and fixed action tray.
- **Slate** (`colors.slate`): Secondary controls and outlined original-listing actions.
- **Soft Slate** (`colors.slate-soft`): The middle line of the role-language front.
- **Steel** (`colors.steel`): Receding role language and low-emphasis editorial type.
- **Mineral Rule** (`colors.rule`): Default dividers across ledgers, panels and typography baselines.
- **Dossier Rule** (`colors.rule-dark`): Separators on the dark search rail.

### Functional

- **Case Note Ochre** (`colors.warning`): Warnings and the visible focus outline on light surfaces.
- **Dark-Surface Focus Mint** (`colors.focus-dark`): Keyboard focus on deep-slate controls.
- **Evidence Exception Red** (`colors.danger`): Invalid or failed evidence states only.

### Named Rules

**The Evidence Signal Rule.** Eucalyptus is controlled, not atmospheric. Use it for verified evidence, live state, selected tabs and the primary action; do not wash whole screens in it.

**The Two Focus Worlds Rule.** Light and dark surfaces use separate focus tokens. Never reuse the ochre light-surface ring inside the dossier or the mint dossier ring on mineral paper.

## Typography

**Display Font:** JobForge Display, the self-hosted Barlow Condensed SemiBold asset, with Arial Narrow and sans-serif fallbacks.  
**Body Font:** Avenir Next, with Avenir, Segoe UI, Helvetica, Arial and sans-serif fallbacks.

**Character:** Condensed role typography gives ambition physical scale while the UI face keeps evidence dense, sober and readable. Weight, case and rules—not multiple decorative families—create hierarchy.

### Hierarchy

- **Display** (`typography.display`): Uppercase language-front phrases, balanced to roughly 9–10 characters per line and intentionally tight at a 0.77 line height.
- **Headline** (`typography.headline`): Uppercase section fronts such as Opportunity Shortlist; it remains condensed and rule-aligned at smaller scale.
- **Title** (`typography.title`): Opportunity titles and other high-confidence row labels.
- **Body** (`typography.body`): Explanations, evidence and dossier guidance, normally held to 40–56 characters per line in major summaries.
- **Label** (`typography.label`): Provenance, recommendation and status language; use uppercase only for short evidence labels, not paragraphs.

### Named Rules

**The Monument and Ledger Rule.** Condensed type belongs to the language front, section headlines and large metrics. Evidence detail remains in the UI face so the interface never becomes a wall of display type.

## Layout

The desktop shell uses a deep-slate search rail sized with `clamp(370px, 31vw, 455px)` and a mineral-paper workspace capped at 1460px. The rail is the stable definition zone; the workspace is the resolving evidence zone. Its primary search action is held in a fixed bottom tray that matches the rail width and includes safe-area bottom padding.

The first viewport pairs the monumental language front with a summary column using `minmax(0, 1fr) minmax(260px, 0.48fr)`. Results are full-width ledger rows, not a tile grid. Opportunity detail may use measured two-column splits, while provenance, checks and metadata stay aligned to rules.

At 980px, the search rail becomes an `min(88vw, 420px)` drawer, the language front and opportunity rows stack, and four-column evidence checks reduce to two columns. At 640px, the canvas uses 1rem side padding, the language front scales to `clamp(3.25rem, 19vw, 5rem)`, actions stack vertically and evidence checks become one column. Touch actions remain at least 44px high.

**The Rail-and-Front Rule.** Preserve the 31% dossier anchor on desktop and the fixed action tray inside it; do not move the primary search action into a generic toolbar or content card.

**The Ledger Rule.** Repeated opportunities, provenance and checks align as rows divided by 1px rules. A masonry, bento or multi-card dashboard breaks the system.

## Elevation & Depth

The system is flat by default. Depth comes from tonal contrast, rules and typography, not persistent shadows. Ambient lift is limited to an opportunity-row hover (`0 14px 28px rgba(26, 39, 43, 0.07)`), the dossier's primary search button (`0 12px 30px rgba(4, 18, 25, 0.24)`) and the fixed action tray (`0 -14px 30px rgba(4, 18, 25, 0.22)`).

### Shadow Vocabulary

- **Ledger Hover:** A low, diffuse lift under the active opportunity row; never present at rest.
- **Search Commitment:** A compact dark-surface shadow under the primary action, marking the rail's decisive control.
- **Fixed Tray Separation:** An upward ambient shadow that separates fixed controls from scrolling dossier content.

### Named Rules

**The Flat-by-Default Rule.** Surfaces remain flush at rest. Shadows appear only for hover response or to clarify a fixed layer.

## Shapes

The form language is square and ledger-like. Most sections, cards, tabs, expanders and metadata chips use zero radius and are structured by 1px rules. Interactive controls use one restrained 3px radius so fields remain legible as controls without softening the overall editorial discipline. Evidence scores and live marks are the only recurring circular geometry.

**The Restrained Corner Rule.** Use `rounded.restrained` only for controls, data frames and alerts. Content containers and opportunity rows use `rounded.square`; do not introduce medium or pill radii.

## Components

### Buttons

- **Shape:** Restrained 3px corners, at least 46px high for Streamlit buttons and 44px for direct listing links.
- **Primary:** Controlled Eucalyptus with Mineral White text. The rail version spans the available width and carries the Search Commitment shadow.
- **Hover / Focus:** Primary actions deepen to Deep Eucalyptus; secondary actions fill Slate and lift by 1px. Light-surface focus uses a 3px Case Note Ochre outline with a 3px offset; dossier focus uses Dark-Surface Focus Mint. Transitions settle over 150ms with `ease-out`.
- **Secondary:** Transparent with a 1px Slate border and Slate text. It inverts to Slate with white text on hover.

### Chips

- **Metadata:** Transparent, square labels divided by a right-hand Mineral Rule. They read as ledger columns rather than pills.
- **Selected dossier tags:** Soft Eucalyptus Wash with dark eucalyptus text and no border.

### Cards / Containers

- **Corner Style:** Square by default.
- **Background:** Transparent on Mineral Paper at rest; an opportunity row reveals Mineral White only on hover.
- **Shadow Strategy:** No resting shadow; use the Ledger Hover token only for the active row.
- **Border:** One bottom rule per opportunity row; panels begin with a Carbon or Mineral Rule.
- **Internal Padding:** Opportunity rows use 1rem vertically and no horizontal card inset.

### Inputs / Fields

- **Style:** Deep dossier fields use a `#1c3442` fill, a deliberate 1px `#7f969e` boundary and restrained 3px corners. Text is near-white and placeholders remain visibly lighter than the field.
- **Focus:** The boundary shifts to `#75b6aa` and gains a `0 0 0 3px rgba(117, 182, 170, 0.24)` ring. The ring supplements the boundary; it does not replace it.
- **Error / Disabled:** Evidence failures use Evidence Exception Red and explicit status language. Never communicate validity by colour alone.

### Navigation

Tabs are transparent, square and rule-aligned. Inactive labels use muted slate; the active tab uses Carbon with a 2px Eucalyptus underline. The search rail becomes Streamlit's collapsible drawer below the desktop breakpoint.

### Opportunity Ledger Row

Each row contains an opportunity title and company, rule-divided metadata, a circular evidence score, an uppercase recommendation and an outlined link to the original listing. At 980px it becomes a stacked row, but source, score and original-listing access remain visible.

### Role-Language Front

The signature display presents broad intent as three rule-underlined uppercase lines that move from Carbon through Soft Slate to Steel. When motion is allowed, the lines settle from the right over 560ms using `cubic-bezier(0.16, 1, 0.3, 1)` with 70ms staggering. Under `prefers-reduced-motion: reduce`, no entrance animation runs.

## Do's and Don'ts

### Do:

- **Do** preserve the mineral-paper workspace, deep-slate dossier and controlled eucalyptus evidence signal.
- **Do** use the self-hosted Barlow Condensed SemiBold asset for monumental role language and condensed section fronts.
- **Do** keep source provenance, evidence scoring, validation state and original-listing access visible in the primary scan path.
- **Do** preserve separate light- and dark-surface focus tokens, strong input boundaries and 44px minimum touch actions.
- **Do** adapt at the established 980px and 640px breakpoints and respect reduced-motion preferences.

### Don't:

- **Don't** turn the interface into a generic recruitment-card, bento or floating-widget dashboard.
- **Don't** use persistent elevation, glossy gradients, pill-heavy controls or large-radius containers.
- **Don't** use eucalyptus as decoration or as a broad background wash; it is an evidence and action signal.
- **Don't** hide provenance, eligibility, score rationale or original-listing access behind secondary navigation.
- **Don't** invent proof, provider coverage, candidate experience or celebratory gamification.
