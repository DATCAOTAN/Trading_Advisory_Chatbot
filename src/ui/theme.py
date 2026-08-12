"""Shared presentation primitives for the Streamlit trading workspace."""

from __future__ import annotations

from html import escape

import streamlit as st


WORKSPACE_CSS = """
<style>
:root {
    --workspace-bg: #f4f7fb;
    --workspace-surface: #ffffff;
    --workspace-surface-muted: #f8fafc;
    --workspace-ink: #172033;
    --workspace-muted: #64748b;
    --workspace-line: #dbe3ee;
    --workspace-accent: #1261a0;
    --workspace-accent-strong: #0b4778;
    --workspace-sidebar: #111827;
}

html, body, [class*="css"] {
    font-family: Inter, "Segoe UI", Arial, sans-serif;
    color: var(--workspace-ink);
}

.stApp { background: var(--workspace-bg); }

.block-container {
    max-width: 1480px;
    padding-top: 1rem;
    padding-bottom: 3rem;
}

[data-testid="stHeader"] { background: rgba(244, 247, 251, 0.92); }
[data-testid="stToolbar"] { right: 0.75rem; }

section[data-testid="stSidebar"] {
    background: var(--workspace-sidebar);
    border-right: 1px solid #263244;
}

section[data-testid="stSidebar"] * { color: #e5e7eb; }
section[data-testid="stSidebar"] hr { border-color: #263244; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #94a3b8; }
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    font-size: 0.95rem;
    line-height: 1.25;
}
section[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: #182235 !important;
    border-color: #334155 !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"],
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #f8fafc;
}
section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    min-height: 2.35rem;
    border: 1px solid #334155;
    border-radius: 6px;
    background: #182235;
    color: #f8fafc;
    font-weight: 600;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #22314a;
    border-color: #60a5fa;
}

.workspace-brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin: 0.1rem 0 1.1rem;
}
.workspace-brand-mark {
    display: grid;
    place-items: center;
    width: 2.15rem;
    height: 2.15rem;
    border-radius: 6px;
    background: #e7f1fb;
    color: #0b4778 !important;
    font-weight: 800;
}
.workspace-brand strong { display: block; color: #f8fafc; font-size: 0.93rem; }
.workspace-brand span { color: #94a3b8 !important; font-size: 0.72rem; }

.workspace-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.2rem 0 1rem;
    border-bottom: 1px solid var(--workspace-line);
    margin-bottom: 0.35rem;
}
.workspace-header h1 {
    margin: 0;
    color: var(--workspace-ink);
    font-size: 1.45rem;
    line-height: 1.25;
    letter-spacing: 0;
}
.workspace-header p {
    margin: 0.3rem 0 0;
    color: var(--workspace-muted);
    font-size: 0.82rem;
}
.workspace-header-meta {
    color: var(--workspace-muted);
    font-size: 0.75rem;
    white-space: nowrap;
}

.workspace-section-heading { margin: 0 0 1rem; }
.workspace-section-heading h2 {
    margin: 0;
    color: var(--workspace-ink);
    font-size: 1.25rem;
    line-height: 1.3;
    letter-spacing: 0;
}
.workspace-section-heading p {
    margin: 0.3rem 0 0;
    color: var(--workspace-muted);
    font-size: 0.82rem;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 1.25rem;
    border-bottom: 1px solid var(--workspace-line);
}
.stTabs [data-baseweb="tab"] {
    min-height: 2.75rem;
    padding: 0 0.15rem;
    color: var(--workspace-muted);
    font-weight: 600;
}
.stTabs [aria-selected="true"] { color: var(--workspace-accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--workspace-accent); }

[data-testid="stMetric"] {
    min-height: 5rem;
    padding: 0.75rem 0.85rem;
    background: var(--workspace-surface);
    border: 1px solid var(--workspace-line);
    border-radius: 6px;
}
[data-testid="stMetricLabel"] { color: var(--workspace-muted); }
[data-testid="stMetricValue"] { color: var(--workspace-ink); font-size: 1.35rem; }

[data-testid="stChatMessage"] {
    padding: 0.85rem 1rem;
    margin-bottom: 0.65rem;
    background: var(--workspace-surface);
    border: 1px solid var(--workspace-line);
    border-radius: 6px;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: #f0f5fa;
    border-color: #d5e1ee;
}
[data-testid="stChatInput"] {
    background: var(--workspace-surface);
    border-color: #bac8d8;
    border-radius: 6px;
}

[data-testid="stExpander"] {
    background: var(--workspace-surface);
    border: 1px solid var(--workspace-line);
    border-radius: 6px;
}
[data-testid="stAlert"] { border-radius: 6px; }
[data-testid="stDataFrame"] { border: 1px solid var(--workspace-line); border-radius: 6px; }

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
    min-height: 2.4rem;
    border-radius: 6px;
    font-weight: 600;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background: var(--workspace-accent);
    border-color: var(--workspace-accent);
}
.stButton > button[kind="primary"]:hover { background: var(--workspace-accent-strong); }

[data-baseweb="input"],
[data-baseweb="select"] > div,
[data-baseweb="textarea"] {
    border-radius: 6px !important;
}

h1, h2, h3, h4, h5, h6 { letter-spacing: 0; }
h3 { font-size: 1.1rem; }
h4 { font-size: 0.95rem; }
hr { border-color: var(--workspace-line); margin: 1.25rem 0; }
code, pre { font-size: 0.78rem; }

.badge {
    display: inline-flex;
    align-items: center;
    min-height: 1.35rem;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0;
    margin-bottom: 0.35rem;
}
.badge-rag { background: #e7f1fb; color: #0b4778; border: 1px solid #bfd7ec; }
.badge-trash { background: #fff1e8; color: #9a3412; border: 1px solid #fed7aa; }
.badge-greet { background: #f1edfb; color: #5b3ea6; border: 1px solid #d8ccf0; }

.source-card {
    background: var(--workspace-surface-muted);
    border: 1px solid var(--workspace-line);
    border-radius: 6px;
    padding: 0.75rem 0.85rem;
    margin: 0.4rem 0;
    font-size: 0.8rem;
}
.source-card strong { color: var(--workspace-accent-strong); }

@media (max-width: 900px) {
    .block-container { padding: 0.75rem 0.8rem 2rem; }
    .workspace-header { align-items: flex-start; flex-direction: column; }
    .workspace-header-meta { white-space: normal; }
    .stTabs [data-baseweb="tab-list"] { gap: 0.8rem; overflow-x: auto; }
    [data-testid="stHorizontalBlock"] { gap: 0.55rem; }
}

@media (max-width: 640px) {
    .workspace-header h1 { font-size: 1.2rem; }
    [data-testid="stMetric"] { min-height: 4.4rem; padding: 0.6rem; }
    [data-testid="stMetricValue"] { font-size: 1.1rem; }
    [data-testid="stChatMessage"] { padding: 0.7rem 0.75rem; }
}
</style>
"""


def apply_workspace_theme() -> None:
    st.markdown(WORKSPACE_CSS, unsafe_allow_html=True)


def render_workspace_header(*, model_name: str, message_count: int) -> None:
    st.markdown(
        f"""
        <header class="workspace-header">
            <div>
                <h1>Trading Advisory Workspace</h1>
                <p>AI research, market context, and controlled MT5 operations</p>
            </div>
            <div class="workspace-header-meta">
                {escape(model_name)} &middot; {message_count} conversation events
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="workspace-section-heading">
            <h2>{escape(title)}</h2>
            <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
