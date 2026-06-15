"""
01_Players.py  —  Phase 2
Register players and assign skill ratings.
"""

import streamlit as st
import pandas as pd
from modules.excel_sync import load_sheet
from modules.player_manager import add_player, delete_player, update_player
from modules.ui_helpers import render_logo, grad_style, render_df
from modules import auth

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
    st.info("You can still update each player's *Preferred First Name* to control how teams are labeled in the UI.")
else:
    # Only render the interactive add-player form for admins. When not
    # authenticated, show a simple informational prompt instead — this avoids
    # Streamlit's "Missing Submit Button" warning caused by a form without
    # a submit control.
    if auth.is_admin():
        with st.form("add_player_form", clear_on_submit=True):
            st.subheader("Add a Player")
            col1, col2 = st.columns([2, 1])
            with col1:
                name = st.text_input("Player Name", placeholder="e.g. Rahul Sharma", max_chars=60)
                preferred_first = st.text_input("Preferred First Name (optional)", placeholder="e.g. Rahul", max_chars=30)
            with col2:
                skill = st.slider(
                    "Skill Rating",
                    min_value=1, max_value=10,
                    value=5, step=1,
                    help="1 = Beginner · 10 = Expert",
                )
            pref_options = ["— No preference —"] + sorted(players_df["name"].tolist())
            pref_sel = st.selectbox(
                "Partner Preference (optional)",
                options=pref_options,
                help="Who this player would like to be paired with.",
            )
            submitted = st.form_submit_button("➕ Add Player", width='stretch')

        if submitted:
            try:
                partner_pref = "" if pref_sel == "— No preference —" else pref_sel
                pid = add_player(name, skill, partner_pref=partner_pref, preferred_first_name=preferred_first)
                st.success(f'Player **{name.strip()}** added (ID {pid}, skill {skill}).')
                players_df = load_sheet("Players")
            except (ValueError, RuntimeError) as e:
                st.error(str(e))
    else:
        st.subheader("Add a Player")
        st.info("Admin-only: unlock via the sidebar to add players.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Player list
# ---------------------------------------------------------------------------
st.subheader(f"Registered Players — {len(players_df)}")

if players_df.empty:
    st.info("No players yet. Add your first player above.")
else:
    # Display with formatted columns
    display = players_df[["player_id", "name", "skill_rating", "partner_pref", "team_id"]].copy()
    display.columns = ["ID", "Name", "Skill Rating", "Pref Partner", "Team ID"]
    display["Pref Partner"] = display["Pref Partner"].fillna("—").replace("", "—")
    display["Team ID"] = display["Team ID"].apply(
        lambda x: "—" if (x is None or str(x) == "nan") else int(x)
    )

    # Ensure Skill Rating displays as whole numbers
    display["Skill Rating"] = pd.to_numeric(display["Skill Rating"], errors="coerce").fillna(0).astype(int)

    # Colour-code skill rating via background gradient
    render_df(
        grad_style(display.style, (["Skill Rating"], "skill", 1, 10)),
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
    # Manage players (per-player edit/delete controls)
    # ---------------------------------------------------------------------------
    if not teams_locked:
        st.markdown("---")
        st.subheader("Manage Players")

        if not auth.is_admin():
            st.info("Unlock admin to edit or remove players.")

        for _, row in players_df.iterrows():
            pid = int(row["player_id"])
            pname = str(row["name"]).strip()
            raw_skill = row.get("skill_rating", None)
            if raw_skill is None or str(raw_skill) in ("", "nan", "None"):
                pskill = "—"
            else:
                try:
                    pskill = int(float(raw_skill))
                except Exception:
                    pskill = raw_skill
            ppref = row.get("partner_pref", "") or "—"

            col_main, col_del, col_edit = st.columns([6, 1, 1])
            with col_main:
                st.markdown(f"**{pname}**  ·  Skill: **{pskill}**  ·  Pref: {ppref}")

            if auth.is_admin():
                # Delete (cross) button
                if col_del.button("✖", key=f"del_{pid}", help=f"Remove {pname}"):
                    st.session_state[f"confirm_delete_{pid}"] = True

                # Edit (pencil) button
                if col_edit.button("✎", key=f"edit_{pid}", help=f"Edit {pname}"):
                    st.session_state[f"edit_player_{pid}"] = True

            # Confirmation UI
            if st.session_state.get(f"confirm_delete_{pid}", False):
                st.warning(f"Confirm deletion of **{pname}** (ID {pid}). This will remove the player permanently.")
                c1, c2 = st.columns([1, 1])
                if c1.button("Confirm Delete", key=f"confirm_del_{pid}"):
                    try:
                        delete_player(pid)
                        st.success(f"Removed **{pname}**.")
                        st.session_state[f"confirm_delete_{pid}"] = False
                        st.experimental_rerun()
                    except (ValueError, RuntimeError) as e:
                        st.error(str(e))
                if c2.button("Cancel", key=f"cancel_del_{pid}"):
                    st.session_state[f"confirm_delete_{pid}"] = False

            # Edit form
            if st.session_state.get(f"edit_player_{pid}", False):
                with st.form(f"edit_form_{pid}", clear_on_submit=False):
                    new_name = st.text_input("Name", value=pname, key=f"edit_name_{pid}")
                    try:
                        cur_skill = int(float(pskill))
                    except Exception:
                        cur_skill = 5
                    # Load current preferred first name if present
                    cur_pref_first = row.get("preferred_first_name", "") or ""
                    new_pref_first = st.text_input("Preferred First Name (optional)", value=cur_pref_first, key=f"edit_pref_first_{pid}")
                    new_skill = st.slider(
                        "Skill Rating",
                        min_value=1, max_value=10, value=cur_skill, step=1, key=f"edit_skill_{pid}"
                    )
                    pref_options = ["— No preference —"] + [n for n in players_df["name"].tolist() if n != pname]
                    cur_pref_index = 0
                    cur_pref = row.get("partner_pref", "") or ""
                    if cur_pref and cur_pref in pref_options:
                        cur_pref_index = pref_options.index(cur_pref)
                    new_pref_sel = st.selectbox("Partner Preference (optional)", options=pref_options, index=cur_pref_index, key=f"edit_pref_{pid}")
                    submitted = st.form_submit_button("Save Changes")

                if submitted:
                    partner_pref = "" if new_pref_sel == "— No preference —" else new_pref_sel
                    try:
                        update_player(pid, name=new_name, skill_rating=new_skill, partner_pref=partner_pref, preferred_first_name=new_pref_first)
                        st.success("Saved changes.")
                        st.session_state[f"edit_player_{pid}"] = False
                        st.experimental_rerun()
                    except (ValueError, RuntimeError) as e:
                        st.error(str(e))

