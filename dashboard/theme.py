from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import streamlit as st


DISPLAY_FONT = Path(__file__).with_name("assets") / "BarlowCondensed-SemiBold.ttf"


def _display_font_uri() -> str:
    if not DISPLAY_FONT.exists():
        return ""
    encoded = b64encode(DISPLAY_FONT.read_bytes()).decode("ascii")
    return f"data:font/ttf;base64,{encoded}"


def inject_theme() -> None:
    css = """
    <style>
    @font-face {
        font-family: "JobForge Display";
        src: url("__DISPLAY_FONT__") format("truetype");
        font-style: normal;
        font-weight: 600;
        font-display: swap;
    }

    :root {
        --jf-paper: #f5f6f3;
        --jf-paper-deep: #e9ece8;
        --jf-white: #fcfdfb;
        --jf-carbon: #101418;
        --jf-slate: #263b48;
        --jf-slate-deep: #142936;
        --jf-slate-soft: #38505e;
        --jf-steel: #7f8e94;
        --jf-line: #c9cfcc;
        --jf-line-dark: #71868f;
        --jf-signal: #2b6e66;
        --jf-signal-deep: #20584f;
        --jf-signal-soft: #dcebe6;
        --jf-warning: #76501e;
        --jf-focus-light: #76501e;
        --jf-focus-dark: #8fd4c8;
        --jf-danger: #9b3b3b;
        --jf-radius: 3px;
        --jf-ui: "Avenir Next", Avenir, "Segoe UI", Helvetica, Arial, sans-serif;
        --jf-display: "JobForge Display", "Arial Narrow", sans-serif;
    }

    html { color-scheme: light; }
    body, .stApp { font-family: var(--jf-ui); }
    .stApp {
        background: var(--jf-paper);
        color: var(--jf-carbon);
    }
    .block-container {
        max-width: 1460px;
        padding: 4.65rem clamp(1.25rem, 2.8vw, 3rem) 5rem;
    }
    header[data-testid="stHeader"] {
        background: rgba(245, 246, 243, 0.94);
        border-bottom: 1px solid var(--jf-line);
        backdrop-filter: blur(10px);
    }
    [data-testid="stBaseButton-header"] {
        display: inline-flex !important;
        color: var(--jf-carbon);
    }
    [data-testid="stAppDeployButton"] { display: none; }
    #MainMenu { visibility: hidden; }

    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: var(--jf-carbon);
    }
    h1, h2, h3 { letter-spacing: -0.025em; }
    p { line-height: 1.58; }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] * { color: #536168 !important; }

    [data-testid="stSidebar"] {
        width: clamp(370px, 31vw, 455px) !important;
        min-width: clamp(370px, 31vw, 455px) !important;
        max-width: clamp(370px, 31vw, 455px) !important;
        background: var(--jf-slate-deep);
        border-right: 1px solid var(--jf-line-dark);
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.1rem;
        padding-bottom: 10.5rem;
    }
    [data-testid="stSidebar"] * { color: #f4f7f5; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
        color: #bdc9ca !important;
    }
    [data-testid="stSidebar"] hr { border-color: var(--jf-line-dark); }
    [data-testid="stSidebar"] h3 {
        font-family: var(--jf-display);
        font-size: 1.4rem;
        text-transform: uppercase;
        letter-spacing: 0.045em;
        margin-bottom: 0.1rem;
    }
    .jf-sidebar-brand {
        padding: 0.25rem 0 1.15rem;
        border-bottom: 1px solid var(--jf-line-dark);
        margin-bottom: 1.15rem;
    }
    .jf-sidebar-brand strong {
        display: block;
        font-size: 1.35rem;
        letter-spacing: -0.035em;
    }
    .jf-sidebar-brand span {
        display: block;
        margin-top: 0.25rem;
        color: #bdc9ca;
        font-size: 0.82rem;
        line-height: 1.45;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: transparent !important;
        border: 0;
        border-top: 1px solid var(--jf-line-dark);
        border-radius: 0;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details,
    [data-testid="stSidebar"] [data-testid="stExpander"] details > summary {
        background: transparent !important;
        border-radius: 0;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details > summary {
        padding-left: 0;
        padding-right: 0;
        font-weight: 700;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details > summary:hover {
        background: rgba(220, 235, 230, 0.07) !important;
    }
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] .stTextArea textarea,
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: #1c3442;
        border: 1px solid #7f969e;
        border-radius: var(--jf-radius);
        color: #f8faf9;
    }
    [data-testid="stSidebar"] input::placeholder,
    [data-testid="stSidebar"] textarea::placeholder {
        color: #aebbbd;
        opacity: 1;
    }
    [data-testid="stSidebar"] input:focus,
    [data-testid="stSidebar"] textarea:focus,
    [data-testid="stSidebar"] div[data-baseweb="select"] > div:focus-within {
        border-color: #75b6aa;
        box-shadow: 0 0 0 3px rgba(117, 182, 170, 0.24);
    }
    [data-testid="stSidebar"] div[data-baseweb="tag"] {
        background: #dcebe6;
        border: 0;
    }
    [data-testid="stSidebar"] div[data-baseweb="tag"] span,
    [data-testid="stSidebar"] div[data-baseweb="tag"] svg {
        color: #163e39 !important;
        fill: #163e39 !important;
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] input,
    [data-testid="stSidebar"] div[data-baseweb="select"] svg {
        color: #f8faf9 !important;
        fill: #f8faf9 !important;
    }
    [role="listbox"] {
        background: var(--jf-white) !important;
        border: 1px solid var(--jf-line);
        border-radius: var(--jf-radius);
        box-shadow: 0 16px 36px rgba(20, 41, 54, 0.16);
        padding: 0.3rem;
    }
    [role="listbox"] [role="option"] {
        background: transparent !important;
        border-radius: var(--jf-radius);
    }
    [role="listbox"] [role="option"],
    [role="listbox"] [role="option"] * {
        color: var(--jf-carbon) !important;
    }
    [role="listbox"] [role="option"]:hover,
    [role="listbox"] [role="option"]:focus,
    [role="listbox"] [role="option"][aria-selected="true"] {
        background: var(--jf-signal-soft) !important;
    }
    [role="listbox"] [role="option"][aria-selected="true"],
    [role="listbox"] [role="option"][aria-selected="true"] * {
        color: var(--jf-signal-deep) !important;
        font-weight: 700;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
        background: #1c3442;
        border: 1px dashed #6d858d;
        border-radius: var(--jf-radius);
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        background: transparent !important;
        border-color: #7f969e !important;
        color: #f8faf9 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] div[data-baseweb="input"] {
        background: #1c3442 !important;
        border: 1px solid #7f969e !important;
        border-radius: var(--jf-radius);
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
        background: #1c3442 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button {
        background: var(--jf-slate-deep) !important;
        border-color: var(--jf-line-dark) !important;
        color: #f8faf9 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button:hover {
        background: var(--jf-signal-deep) !important;
    }

    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 48px;
        background: var(--jf-white) !important;
        border: 1px solid var(--jf-slate) !important;
        border-radius: var(--jf-radius);
        color: var(--jf-carbon) !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {
        border-color: var(--jf-signal) !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within {
        border-color: var(--jf-signal) !important;
        box-shadow: 0 0 0 3px rgba(43, 110, 102, 0.18);
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] span,
    [data-testid="stSelectbox"] div[data-baseweb="select"] input {
        color: var(--jf-carbon) !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] svg {
        color: var(--jf-slate) !important;
        fill: var(--jf-slate) !important;
    }

    div.stButton > button,
    div.stDownloadButton > button,
    a[data-testid="stLinkButton"] {
        min-height: 46px;
        border-radius: var(--jf-radius);
        border: 1px solid var(--jf-slate);
        background: transparent;
        color: var(--jf-slate);
        font-weight: 750;
        transition: background 150ms ease-out, color 150ms ease-out, border-color 150ms ease-out, transform 150ms ease-out;
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover,
    a[data-testid="stLinkButton"]:hover {
        background: var(--jf-slate);
        border-color: var(--jf-slate);
        color: #fff;
        transform: translateY(-1px);
    }
    div.stButton > button[kind="primary"],
    div.stDownloadButton > button[kind="primary"] {
        background: var(--jf-signal);
        border-color: var(--jf-signal);
        color: #fff;
    }
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primary"]:hover {
        background: var(--jf-signal) !important;
        border-color: var(--jf-signal) !important;
        color: #fff !important;
    }
    button[data-testid="stBaseButton-primary"] * { color: #fff !important; }
    div.stButton > button[kind="primary"]:hover,
    div.stDownloadButton > button[kind="primary"]:hover {
        background: var(--jf-signal-deep);
        border-color: var(--jf-signal-deep);
    }
    [data-testid="stSidebar"] div.stButton > button {
        border-color: #6b818a;
        color: #f7faf8;
    }
    [data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        background: var(--jf-signal);
        border-color: #65a99e;
        box-shadow: 0 12px 30px rgba(4, 18, 25, 0.24);
    }
    div.stButton > button:focus-visible,
    div.stDownloadButton > button:focus-visible,
    .jf-verify:focus-visible {
        outline: 3px solid var(--jf-focus-light);
        outline-offset: 3px;
    }
    [data-testid="stSidebar"] div.stButton > button:focus-visible,
    [data-testid="stSidebar"] div.stDownloadButton > button:focus-visible {
        outline-color: var(--jf-focus-dark);
    }
    [data-testid="stSidebar"] .st-key-search_action_tray {
        position: fixed;
        z-index: 20;
        left: 0;
        bottom: 0;
        width: clamp(370px, 31vw, 455px);
        padding: 0.75rem 1.5rem calc(1rem + env(safe-area-inset-bottom));
        background: var(--jf-slate-deep);
        border-top: 1px solid var(--jf-line-dark);
        box-shadow: 0 -14px 30px rgba(4, 18, 25, 0.22);
    }
    [data-testid="stSidebar"] .st-key-search_action_tray [data-testid="stNumberInput"] {
        margin-bottom: 0.35rem;
    }
    [data-testid="stSidebar"][aria-expanded="false"] {
        width: 300px !important;
        min-width: 300px !important;
        max-width: 300px !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] .st-key-search_action_tray {
        width: 300px;
    }

    .jf-direction-contract { display: none; }
    .jf-hero {
        border-bottom: 1px solid var(--jf-carbon);
        margin: 0 0 1.7rem;
        padding: 0.2rem 0 1.5rem;
        overflow: hidden;
    }
    .jf-masthead {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding-bottom: 1.05rem;
        border-bottom: 1px solid var(--jf-line);
    }
    .jf-wordmark {
        font-size: 1.32rem;
        font-weight: 820;
        letter-spacing: -0.045em;
    }
    .jf-live-mark {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: #4f6067;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .jf-live-mark::before {
        content: "";
        width: 0.5rem;
        height: 0.5rem;
        border-radius: 50%;
        background: var(--jf-signal);
    }
    .jf-language-front {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(260px, 0.48fr);
        gap: clamp(1.4rem, 4vw, 4rem);
        align-items: end;
        min-height: 275px;
        padding-top: 1.15rem;
    }
    .jf-language-copy h1 {
        margin: 0;
        max-width: 10ch;
        font-family: var(--jf-display);
        font-size: clamp(4.4rem, 8.2vw, 7.8rem);
        font-weight: 600;
        line-height: 0.77;
        letter-spacing: -0.028em;
        text-transform: uppercase;
        text-wrap: balance;
    }
    .jf-language-copy h1 span {
        display: block;
        color: inherit;
        border-bottom: 1px solid var(--jf-line);
    }
    .jf-language-copy h1 span:nth-child(2) { color: var(--jf-slate-soft); }
    .jf-language-summary {
        border-top: 1px solid var(--jf-carbon);
        padding-top: 0.9rem;
        margin-bottom: 0.15rem;
    }
    .jf-language-summary strong {
        display: block;
        font-size: clamp(1.25rem, 2vw, 1.7rem);
        letter-spacing: -0.035em;
        max-width: 18ch;
    }
    .jf-language-summary p {
        color: #536168;
        max-width: 40ch;
        margin: 0.65rem 0 0;
    }

    .jf-empty {
        display: grid;
        grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
        gap: clamp(2rem, 6vw, 6rem);
        border: 0;
        border-bottom: 1px solid var(--jf-line);
        background: transparent;
        border-radius: 0;
        padding: clamp(1rem, 3vw, 2.5rem) 0;
        box-shadow: none;
    }
    .jf-empty h2 {
        font-family: var(--jf-display);
        text-transform: uppercase;
        font-size: clamp(2.7rem, 5vw, 5rem);
        line-height: 0.88;
        margin: 0;
        max-width: 8ch;
    }
    .jf-empty p { color: #536168; max-width: 56ch; }
    .jf-steps { display: grid; grid-template-columns: 1fr; gap: 0; margin: 0; }
    .jf-step {
        display: grid;
        grid-template-columns: minmax(120px, 0.35fr) 1fr;
        gap: 1rem;
        border-top: 1px solid var(--jf-line);
        padding: 0.9rem 0;
    }
    .jf-step strong { color: var(--jf-carbon); }
    .jf-step span { color: #536168; }

    div[data-testid="stMetric"] {
        background: transparent;
        border: 0;
        border-top: 1px solid var(--jf-carbon);
        border-radius: 0;
        padding: 0.75rem 0 1rem;
        box-shadow: none;
    }
    div[data-testid="stMetric"] label { color: #536168; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--jf-carbon);
        font-family: var(--jf-display);
        font-size: 2.8rem;
    }

    .jf-mode-strip {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0;
        min-height: 48px;
        margin: 0 0 1.8rem;
        border-top: 1px solid var(--jf-line);
        border-bottom: 1px solid var(--jf-line);
        font-size: 0.79rem;
    }
    .jf-mode-strip > * { margin-right: 0.75rem; }
    .jf-source {
        border: 0;
        border-left: 1px solid var(--jf-line);
        background: transparent;
        color: var(--jf-signal-deep);
        border-radius: 0;
        padding: 0.15rem 0 0.15rem 0.75rem;
        font-weight: 760;
    }

    .jf-section-title {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 1rem;
        margin: 2.5rem 0 0.85rem;
        padding-bottom: 0.7rem;
        border-bottom: 1px solid var(--jf-carbon);
    }
    .jf-section-title h2 {
        font-family: var(--jf-display);
        text-transform: uppercase;
        font-size: clamp(2rem, 4vw, 3.4rem);
        line-height: 0.9;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .jf-muted { color: #536168 !important; }

    .jf-grid { display: block; margin-bottom: 2.2rem; }
    .jf-card {
        min-height: 0;
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 1.5rem;
        align-items: center;
        background: transparent;
        border: 0;
        border-bottom: 1px solid var(--jf-line);
        border-radius: 0;
        padding: 1rem 0;
        box-shadow: none;
    }
    .jf-card:hover {
        background: var(--jf-white);
        border-color: var(--jf-carbon);
        transform: none;
        box-shadow: 0 14px 28px rgba(26, 39, 43, 0.07);
    }
    .jf-card-top { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; }
    .jf-job-title {
        color: var(--jf-carbon);
        font-size: 1.08rem;
        font-weight: 800;
        line-height: 1.25;
    }
    .jf-company { color: #536168; font-size: 0.88rem; margin-top: 0.15rem; }
    .jf-score {
        min-width: 3.8rem;
        background: transparent;
        color: var(--jf-signal-deep);
        border: 1px solid var(--jf-signal);
        border-radius: 50%;
        padding: 0.65rem 0.35rem;
        text-align: center;
        font-family: var(--jf-display);
        font-size: 1.2rem;
    }
    .jf-score span {
        display: block;
        color: #536168;
        font-family: var(--jf-ui);
        font-size: 0.58rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .jf-meta { display: flex; flex-wrap: wrap; gap: 0; margin: 0.7rem 0 0; }
    .jf-chip {
        background: transparent;
        border: 0;
        border-right: 1px solid var(--jf-line);
        border-radius: 0;
        color: #536168;
        font-size: 0.75rem;
        font-weight: 650;
        padding: 0 0.55rem;
    }
    .jf-chip:first-child { padding-left: 0; }
    .jf-link-row {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.8rem;
        border: 0;
        padding: 0;
    }
    .jf-recommendation {
        color: var(--jf-signal-deep);
        font-size: 0.76rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.045em;
    }
    .jf-verify {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 44px;
        color: var(--jf-slate) !important;
        background: transparent;
        border: 1px solid var(--jf-slate);
        border-radius: var(--jf-radius);
        padding: 0.55rem 0.8rem;
        text-decoration: none !important;
        font-size: 0.78rem;
        font-weight: 800;
        white-space: nowrap;
    }
    .jf-verify:hover { color: #fff !important; background: var(--jf-slate); }

    .jf-panel {
        background: transparent;
        border: 0;
        border-top: 1px solid var(--jf-carbon);
        border-radius: 0;
        padding: 0.85rem 0 1.2rem;
        margin-bottom: 1rem;
    }
    .jf-panel h3 { margin: 0 0 0.7rem; font-size: 1.05rem; }
    .jf-list { margin: 0; padding-left: 1.15rem; }
    .jf-list li { color: #34444b; margin: 0.45rem 0; line-height: 1.48; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 1.2rem;
        border-bottom: 1px solid var(--jf-line);
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 0;
        color: #536168;
        padding-left: 0;
        padding-right: 0;
    }
    .stTabs [aria-selected="true"] {
        color: var(--jf-carbon);
        border-bottom: 2px solid var(--jf-signal);
    }
    [data-testid="stExpander"] {
        background: transparent;
        border: 0;
        border-top: 1px solid var(--jf-line);
        border-radius: 0;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid var(--jf-line);
        border-radius: var(--jf-radius);
        overflow: hidden;
        background: var(--jf-white);
    }
    .jf-check-grid { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid var(--jf-line); }
    .jf-check {
        border: 0;
        border-right: 1px solid var(--jf-line);
        border-radius: 0;
        padding: 0.85rem;
        color: #536168;
    }
    .jf-check:last-child { border-right: 0; }
    .jf-check strong { color: var(--jf-signal-deep); display: block; margin-bottom: 0.2rem; }
    .stAlert { border-radius: var(--jf-radius); }
    .jf-footer {
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid var(--jf-line);
        color: var(--jf-slate-soft);
        font-size: 0.78rem;
        line-height: 1.5;
    }

    @media (prefers-reduced-motion: no-preference) {
        .jf-language-copy h1 span {
            animation: jf-settle 560ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .jf-language-copy h1 span:nth-child(2) { animation-delay: 70ms; }
        @keyframes jf-settle {
            from { transform: translateX(1.2rem); clip-path: inset(0 0 0 12%); }
            to { transform: translateX(0); clip-path: inset(0); }
        }
    }

    @media (max-width: 980px) {
        [data-testid="stSidebar"] {
            width: min(88vw, 420px) !important;
            min-width: min(88vw, 420px) !important;
            max-width: min(88vw, 420px) !important;
        }
        [data-testid="stSidebar"] .st-key-search_action_tray {
            width: min(88vw, 420px);
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .jf-language-front { grid-template-columns: 1fr; min-height: 0; gap: 1.5rem; }
        .jf-language-copy h1 { font-size: clamp(3.9rem, 15vw, 6rem); max-width: 9ch; }
        .jf-language-summary { max-width: 56ch; }
        .jf-empty { grid-template-columns: 1fr; }
        .jf-card { grid-template-columns: 1fr; }
        .jf-link-row { justify-content: space-between; }
        .jf-check-grid { grid-template-columns: repeat(2, 1fr); }
        .jf-check:nth-child(2) { border-right: 0; }
    }

    @media (max-width: 640px) {
        .block-container { padding: 4.2rem 1rem 3.5rem; }
        .jf-masthead { align-items: flex-start; }
        .jf-live-mark { text-align: right; }
        .jf-hero { margin-bottom: 1.2rem; }
        .jf-language-front { padding-top: 0.9rem; }
        .jf-language-copy h1 { font-size: clamp(3.25rem, 19vw, 5rem); line-height: 0.82; }
        .jf-language-summary strong { font-size: 1.2rem; }
        .jf-empty h2 { font-size: 3.2rem; }
        .jf-step { grid-template-columns: 1fr; gap: 0.25rem; }
        .jf-section-title { display: block; }
        .jf-section-title .jf-muted { display: block; margin-top: 0.45rem; }
        .jf-card-top { grid-template-columns: 1fr auto; }
        .jf-link-row { align-items: stretch; flex-direction: column; }
        .jf-verify { text-align: center; }
        .jf-check-grid { grid-template-columns: 1fr; }
        .jf-check, .jf-check:nth-child(2) { border-right: 0; border-bottom: 1px solid var(--jf-line); }
    }
    </style>
    """.replace("__DISPLAY_FONT__", _display_font_uri())
    st.markdown(css, unsafe_allow_html=True)
