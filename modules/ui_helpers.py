"""
ui_helpers.py
Shared UI utilities: global CSS, logo display, colormaps.
"""

import streamlit as st
from pathlib import Path
from matplotlib.colors import LinearSegmentedColormap
from .excel_sync import LOCATIONS, set_location
from . import auth

_LOGO_DIR     = Path(__file__).parent.parent / "assets" / "logo"
_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# ---------------------------------------------------------------------------
# Colormaps
# ---------------------------------------------------------------------------
CMAP_WINS   = LinearSegmentedColormap.from_list("dark_greens", ["#23263A", "#22C55E"])
CMAP_LOSSES = LinearSegmentedColormap.from_list("dark_reds",   ["#23263A", "#EF4444"])
CMAP_AWARDS = LinearSegmentedColormap.from_list("dark_amber",  ["#23263A", "#F59E0B"])
CMAP_SKILL  = LinearSegmentedColormap.from_list("dark_rdylgn", ["#EF4444", "#23263A", "#22C55E"])

# ---------------------------------------------------------------------------
# CSS (dark)
# ---------------------------------------------------------------------------
_CSS_SHARED = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}

/* ── Global text colour (must beat the dark base from config.toml) ── */
body, p, span, div, li, td, th, label, small, strong, em,
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] *,
[data-testid="stText"],
[data-testid="stHeadingWithActionElements"] *,
[data-testid="stWidgetLabel"] *,
.stAlert p,
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span {{
    color: {text} !important;
}}

/* Inputs */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] *,
[data-testid="stRadio"] *,
[data-testid="stCheckbox"] * {{
    color: {text} !important;
}}

/* Sidebar text */
[data-testid="stSidebar"],
[data-testid="stSidebar"] * {{
    color: {text} !important;
}}

[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}

/* Location selectbox — block typing, keep click-to-open */
[data-testid="stSidebar"] [data-testid="stSelectbox"] input {{
    pointer-events: none !important;
    caret-color: transparent !important;
}}

[data-testid="stLogo"] img {{
    width: 200px !important;
    max-width: none !important;
    height: auto !important;
}}

h1 {{ font-weight: 800 !important; letter-spacing: -0.025em !important; }}
h2, h3 {{ font-weight: 600 !important; letter-spacing: -0.01em !important; }}

[data-testid="stCaptionContainer"] p {{
    font-size: 0.9rem !important;
    color: {muted} !important;
}}

hr {{
    border: none !important;
    border-top: 1px solid {border} !important;
    margin: 1.8rem 0 !important;
}}

[data-testid="metric-container"] {{
    background: linear-gradient(135deg, {card1} 0%, {card2} 100%) !important;
    border: 1px solid {border} !important;
    border-left: 3px solid #C00000 !important;
    border-radius: 14px !important;
    padding: 1.2rem 1.5rem !important;
    box-shadow: 0 2px 12px {shadow} !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}
[data-testid="metric-container"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 22px rgba(192,0,0,0.18) !important;
}}
[data-testid="stMetricLabel"] {{
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: {muted} !important;
}}
[data-testid="stMetricValue"] {{
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: {text} !important;
}}

.stButton > button {{
    background: linear-gradient(135deg, #C00000 0%, #960000 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.03em !important;
    padding: 0.55rem 1.6rem !important;
    box-shadow: 0 2px 10px rgba(192,0,0,0.35) !important;
    transition: all 0.18s ease !important;
}}
.stButton > button:hover {{
    background: linear-gradient(135deg, #D40000 0%, #B00000 100%) !important;
    box-shadow: 0 4px 18px rgba(192,0,0,0.5) !important;
    transform: translateY(-1px) !important;
}}
.stButton > button:active {{
    transform: translateY(0) !important;
    box-shadow: 0 2px 8px rgba(192,0,0,0.3) !important;
}}

[data-testid="stExpander"] {{
    border: 1px solid {border} !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    background: {expander_bg} !important;
}}
/* Force expander inner elements — dark base theme overrides these otherwise */
[data-testid="stExpander"] details {{
    background: {expander_bg} !important;
}}
[data-testid="stExpander"] details > summary {{
    background: {expander_bg} !important;
    color: {text} !important;
    border-bottom: 1px solid {border} !important;
}}
[data-testid="stExpander"] details > summary:hover {{
    background: {card2} !important;
}}
[data-testid="stExpander"] details > summary span,
[data-testid="stExpander"] details > summary p,
[data-testid="stExpander"] details > summary * {{
    color: {text} !important;
}}
[data-testid="stExpanderDetails"] {{
    background: {expander_bg} !important;
    color: {text} !important;
}}
[data-testid="stExpander"] summary {{
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 0.6rem 0.8rem !important;
}}

/* ── Forms ── */
[data-testid="stForm"] {{
    background: {expander_bg} !important;
    border: 1px solid {border} !important;
    border-radius: 12px !important;
    padding: 1rem !important;
}}
[data-testid="stForm"] * {{
    color: {text} !important;
}}

/* ── All interactive widget containers ── */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span {{
    color: {text} !important;
}}
[data-testid="stTextInput"] > div,
[data-testid="stNumberInput"] > div,
[data-testid="stSelectbox"] > div {{
    background: {card1} !important;
    color: {text} !important;
}}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] input,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
    background: {card1} !important;
    color: {text} !important;
}}

[data-testid="stAlert"] {{
    border-radius: 12px !important;
    border-left-width: 4px !important;
}}

[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {{
    border-radius: 9px !important;
    border-color: {border} !important;
}}

[data-testid="stDataFrame"] {{
    border: 1px solid {border} !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}}

[data-testid="stRadio"] label {{ font-weight: 500 !important; }}

[data-testid="stTabs"] [role="tab"] {{
    font-weight: 500 !important;
    border-radius: 8px 8px 0 0 !important;
}}

[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
[data-testid="stSidebar"] > div > div,
[data-testid="stSidebarContent"] {{
    background: {sidebar_bg} !important;
    background-color: {sidebar_bg} !important;
    --text-color: {text};
}}
[data-testid="stSidebar"] {{
    border-right: 1px solid {border} !important;
}}
/* Force ALL sidebar text dark/light */
[data-testid="stSidebar"] :is(a, p, span, li, div, label, h1, h2, h3, h4, h5, h6, small) {{
    color: {text} !important;
}}
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p {{
    color: {text} !important;
}}
[data-testid="stSidebarNav"] li > a {{
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: background 0.15s, color 0.15s !important;
    color: {text} !important;
}}
[data-testid="stSidebarNav"] li > a:hover {{
    background: rgba(192,0,0,0.14) !important;
    color: #FF5555 !important;
}}

/* Main content area */
[data-testid="stAppViewContainer"] > .main {{
    background-color: {bg} !important;
}}
[data-testid="stAppViewContainer"] {{
    background-color: {bg} !important;
}}
body, [data-testid="stApp"] {{
    background-color: {bg} !important;
    color: {text} !important;
}}

/* ── Download button pinned to sidebar bottom ── */
[data-testid="stSidebar"] [data-testid="stDownloadButton"] {{
    position: fixed !important;
    bottom: 1rem !important;
    left: 1rem !important;
    width: auto !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    z-index: 999 !important;
}}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button {{
    width: 44px !important;
    height: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    border-radius: 10px !important;
    font-size: 1.3rem !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.35) !important;
    position: relative !important;
}}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button::after {{
    content: "Export Excel" !important;
    position: absolute !important;
    left: calc(100% + 10px) !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    background: {card2} !important;
    color: {text} !important;
    border: 1px solid {border} !important;
    padding: 4px 10px !important;
    border-radius: 6px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
    opacity: 0 !important;
    pointer-events: none !important;
    transition: opacity 0.15s ease !important;
}}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button:hover::after {{
    opacity: 1 !important;
}}

"""

_DARK = dict(
    bg="#1A1D2E",
    card1="#23263A",
    card2="#282C44",
    border="#373B57",
    text="#E4E6F0",
    muted="#8892B0",
    sidebar_bg="#161827",
    shadow="rgba(0,0,0,0.25)",
    expander_bg="#1E2138",
)

_CSS = "<style>" + _CSS_SHARED.format(**_DARK) + "</style>"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_cmaps() -> dict:
    return dict(wins=CMAP_WINS, losses=CMAP_LOSSES, awards=CMAP_AWARDS, skill=CMAP_SKILL)


def render_logo() -> None:
    """Inject CSS, render location selector, and render the sidebar logo."""
    st.markdown(_CSS, unsafe_allow_html=True)

    # Location selector — must happen before any data call on every page
    if "_location" not in st.session_state:
        st.session_state["_location"] = LOCATIONS[0]

    selected = st.sidebar.selectbox(
        "\U0001f4cd Location",
        LOCATIONS,
        index=LOCATIONS.index(st.session_state["_location"]),
        key="_loc_select",
    )
    if selected != st.session_state["_location"]:
        st.session_state["_location"] = selected
        st.rerun()
    set_location(st.session_state["_location"])

    # Admin login (shows unlock widget in the sidebar)
    try:
        auth.admin_widget()
    except Exception:
        pass

    # Sync-to-GitHub button (admin only)
    if auth.is_admin():
        from modules.excel_sync import sync_to_github
        if st.sidebar.button("☁️ Sync to GitHub", key="sidebar_sync", width="stretch"):
            result = sync_to_github()
            if result["pushed"]:
                st.sidebar.success(f"✅ Synced {len(result['pushed'])} sheet(s) to GitHub")
            elif result["failed"]:
                st.sidebar.warning(f"⚠️ Sync failed for: {', '.join(result['failed'])}")
            else:
                st.sidebar.info("Nothing to sync — data is up to date")

    # Logo
    logo_file = None
    if _LOGO_DIR.exists():
        for f in sorted(_LOGO_DIR.iterdir()):
            if f.suffix.lower() in _ALLOWED_EXTS:
                logo_file = f
                break
    if logo_file:
        st.logo(str(logo_file), size="large")

    # Download Excel button (always at bottom of sidebar)
    _render_download_button()


def _render_download_button() -> None:
    """Render a sidebar button pinned to the bottom to download the active location's Excel file."""
    # Build the workbook in-memory from current CSVs and offer it for download.
    from modules.excel_export import generate_workbook_bytes
    loc = st.session_state.get("_location", LOCATIONS[0])
    data_dir = Path(__file__).parent.parent / "data" / loc.lower()
    if data_dir.exists() and any(f.suffix.lower() == ".csv" for f in data_dir.iterdir()):
        data = generate_workbook_bytes(loc)
        filename = f"tournament_{loc.lower()}.xlsx"
        st.sidebar.download_button(
            label="📥",
            data=data,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.sidebar.caption("No data file yet for this location.")


def render_df(styler_or_df, hide_index: bool = True) -> None:
    st.dataframe(styler_or_df, width='stretch', hide_index=hide_index)
