"""
01_Players.py  —  Phase 2
Register players and assign skill ratings.
"""

import streamlit as st
from modules.excel_sync import load_sheet
from modules.player_manager import add_player, delete_player
from modules.ui_helpers import render_logo, get_cmaps, render_df

st.set_page_config(page_title="Players · Carrom Tournament", page_icon="👤", layout="wide", initial_sidebar_state="expanded")
render_logo()

st.title("👤 Player Registration")
st.caption("Add all participants before building teams. Minimum 4 players, even count required.")
st.markdown("---")

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def _reload():
    st.session_state["players_df"] = load_sheet("Players")

if "players_df" not in st.session_state:
    _reload()

players_df = load_sheet("Players")
teams_exist = not load_sheet("Teams").empty
teams_locked = teams_exist  # once teams are built, player list is locked

# ---------------------------------------------------------------------------
# Add player form
# ---------------------------------------------------------------------------
if teams_locked:
    st.warning("Teams have been built — player list is locked. Reset teams on the **Teams** page to make changes.")
else:
    with st.form("add_player_form", clear_on_submit=True):
        st.subheader("Add a Player")
        col1, col2 = st.columns([2, 1])
        with col1:
            name = st.text_input("Player Name", placeholder="e.g. Rahul Sharma", max_chars=60)
        with col2:
            skill = st.slider(
                "Skill Rating",
                min_value=1.0, max_value=10.0,
                value=5.0, step=0.5,
                help="1 = Beginner · 10 = Expert",
            )
        submitted = st.form_submit_button("➕ Add Player", use_container_width=True)

    if submitted:
        try:
            pid = add_player(name, skill)
            st.success(f'Player **{name.strip()}** added (ID {pid}, skill {skill}).')
            players_df = load_sheet("Players")
        except (ValueError, RuntimeError) as e:
            st.error(str(e))

st.markdown("---")

# ---------------------------------------------------------------------------
# Player list
# ---------------------------------------------------------------------------
st.subheader(f"Registered Players — {len(players_df)}")

if players_df.empty:
    st.info("No players yet. Add your first player above.")
else:
    # Display with formatted columns
    display = players_df[["player_id", "name", "skill_rating", "team_id"]].copy()
    display.columns = ["ID", "Name", "Skill Rating", "Team ID"]
    display["Team ID"] = display["Team ID"].apply(
        lambda x: "—" if (x is None or str(x) == "nan") else int(x)
    )

    # Colour-code skill rating via background gradient
    render_df(
        display.style.background_gradient(subset=["Skill Rating"], cmap=get_cmaps()["skill"], vmin=1, vmax=10),
    )

    # Player count status
    n = len(players_df)
    if n < 4:
        st.warning(f"{n} player(s) registered — need at least 4 to build teams.")
    elif n % 2 != 0:
        st.warning(f"{n} players registered — need an **even** number for 2v2 teams.")
    else:
        st.success(f"{n} players registered — ready to build **{n // 2} teams** on the Teams page.")

    # ---------------------------------------------------------------------------
    # Delete a player (only before teams are formed)
    # ---------------------------------------------------------------------------
    if not teams_locked:
        st.markdown("---")
        st.subheader("Remove a Player")
        name_map = {
            f"{row['name']} (ID {int(row['player_id'])})": int(row["player_id"])
            for _, row in players_df.iterrows()
        }
        selected = st.selectbox("Select player to remove", options=list(name_map.keys()))
        if st.button("🗑️ Remove Player", type="secondary"):
            try:
                delete_player(name_map[selected])
                st.success(f"Removed **{selected}**.")
                st.rerun()
            except (ValueError, RuntimeError) as e:
                st.error(str(e))

