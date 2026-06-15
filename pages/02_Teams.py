"""
02_Teams.py  —  Phase 2
View balanced team pairings and assign custom team names.
"""

import pandas as pd
import streamlit as st
from modules.excel_sync import load_sheet
from modules.team_builder import build_balanced_teams, get_default_pairing, rename_team, reset_teams, get_team_players
from modules.ui_helpers import render_logo, grad_style, render_df
from modules import auth

render_logo()

st.title("🤝 Teams")
st.caption("Auto-balanced 2v2 teams based on skill ratings. Rename teams after building.")
st.markdown("---")

# ---------------------------------------------------------------------------
# Load current state
# ---------------------------------------------------------------------------
players_df  = load_sheet("Players")
teams_df    = load_sheet("Teams")
matches_df  = load_sheet("Matches")

teams_exist    = not teams_df.empty
matches_exist  = not matches_df.empty
n_players      = len(players_df)

# ---------------------------------------------------------------------------
# Build Teams section
# ---------------------------------------------------------------------------
if not teams_exist:
    st.subheader("Build Balanced Teams")

    if n_players < 4:
        st.warning(f"Only {n_players} player(s) registered. Head to **Players** and add at least 4.")
    elif n_players % 2 != 0:
        st.warning(
            f"{n_players} players registered \u2014 need an **even** number for 2v2. "
            "Head to **Players** to add one more."
        )
    else:
        # ------------------------------------------------------------------
        # Initialise / validate the working pairing in session state.
        # Reset whenever the player roster changes.
        # ------------------------------------------------------------------
        _player_id_set = tuple(sorted(players_df["player_id"].astype(int).tolist()))
        if (
            "proposed_pairs" not in st.session_state
            or st.session_state.get("proposed_pairs_players") != _player_id_set
        ):
            default = get_default_pairing(players_df)
            st.session_state["proposed_pairs"]         = [list(p) for p in default]
            st.session_state["proposed_pairs_players"] = _player_id_set

        pairs = st.session_state["proposed_pairs"]
        players_map = {int(row["player_id"]): row for _, row in players_df.iterrows()}

        # ------------------------------------------------------------------
        # Build preview rows with preference indicators
        # ------------------------------------------------------------------
        def _pref_label(player_row, partner_row) -> str:
            pref = str(player_row["partner_pref"] or "").strip()
            name = str(player_row["name"])
            if not pref:
                return name
            if pref.lower() == str(partner_row["name"]).lower():
                return f"{name} \U0001f7e2"  # 🟢
            return f"{name} \U0001f7e1"      # 🟡

        preview_rows = []
        for i, (pid1, pid2) in enumerate(pairs):
            p1, p2 = players_map[pid1], players_map[pid2]
            try:
                s1 = int(float(p1["skill_rating"]))
            except Exception:
                s1 = 0
            try:
                s2 = int(float(p2["skill_rating"]))
            except Exception:
                s2 = 0
            avg = int(round((s1 + s2) / 2))
            preview_rows.append({
                "Team":      f"Team {chr(65 + i)}",
                "Player 1":  _pref_label(p1, p2),
                "Skill 1":   s1,
                "Player 2":  _pref_label(p2, p1),
                "Skill 2":   s2,
                "Avg Skill": avg,
            })

        preview_df = pd.DataFrame(preview_rows)
        hdr_col, legend_col = st.columns([3, 1])
        with hdr_col:
            st.markdown("**Proposed pairings:**")
        with legend_col:
            st.caption("\U0001f7e2 pref met \u00b7 \U0001f7e1 pref not met")
        render_df(grad_style(preview_df.style, (["Avg Skill"], "skill", 1, 10)))

        spread    = int(preview_df["Avg Skill"].max() - preview_df["Avg Skill"].min())
        prefs_met = sum(
            1 for r in preview_rows
            if "\U0001f7e2" in r["Player 1"] or "\U0001f7e2" in r["Player 2"]
        )
        st.caption(f"Skill spread: **{spread}** pts \u00b7 **{prefs_met}** preference(s) satisfied")

        # ------------------------------------------------------------------
        # Manual swap UI
        # ------------------------------------------------------------------
        with st.expander("\u21c4 Adjust Pairings", expanded=True):
            st.caption(
                "Swap any two players between teams to accommodate preferences. "
                "Avg skills update instantly."
            )
            all_names   = [str(row["name"]) for _, row in players_df.iterrows()]
            name_to_pid = {str(row["name"]): int(row["player_id"]) for _, row in players_df.iterrows()}

            sc1, sc2, sc3 = st.columns([2, 2, 1])
            with sc1:
                swap_a = st.selectbox("Player A", options=all_names, key="swap_sel_a")
            with sc2:
                swap_b = st.selectbox("Player B", options=all_names, key="swap_sel_b")
            with sc3:
                st.write("")
                do_swap = st.button("\u21c4 Swap", use_container_width=True)

            if do_swap:
                pid_a = name_to_pid[swap_a]
                pid_b = name_to_pid[swap_b]
                if pid_a == pid_b:
                    st.warning("Select two **different** players to swap.")
                else:
                    idx_a = next((i for i, p in enumerate(pairs) if pid_a in p), None)
                    idx_b = next((i for i, p in enumerate(pairs) if pid_b in p), None)
                    if idx_a is None or idx_b is None:
                        st.warning("Player not found in any pairing \u2014 try resetting.")
                    elif idx_a == idx_b:
                        st.info("Those players are already on the same team.")
                    else:
                        new_pairs = [list(p) for p in pairs]
                        pos_a = new_pairs[idx_a].index(pid_a)
                        pos_b = new_pairs[idx_b].index(pid_b)
                        new_pairs[idx_a][pos_a] = pid_b
                        new_pairs[idx_b][pos_b] = pid_a
                        st.session_state["proposed_pairs"] = new_pairs
                        st.rerun()

            if st.button("\u21ba Reset to balanced", use_container_width=True):
                st.session_state.pop("proposed_pairs", None)
                st.session_state.pop("proposed_pairs_players", None)
                st.rerun()

        # ------------------------------------------------------------------
        # Confirm & Build
        # ------------------------------------------------------------------
        if auth.is_admin():
            if st.button("\u2705 Confirm & Build Teams", type="primary", width='stretch'):
                try:
                    build_balanced_teams(custom_pairing=[(p[0], p[1]) for p in pairs])
                    st.success(f"Built **{len(pairs)} balanced teams** successfully!")
                    st.session_state.pop("proposed_pairs", None)
                    st.session_state.pop("proposed_pairs_players", None)
                    st.rerun()
                except (RuntimeError, ValueError) as e:
                    st.error(str(e))
        else:
            st.info("Unlock admin to build teams.")

else:
    # ---------------------------------------------------------------------------
    # Teams are built — show roster cards + rename controls
    # ---------------------------------------------------------------------------
    st.subheader(f"Teams — {len(teams_df)} formed")

    for _, team in teams_df.iterrows():
        team_id   = int(team["team_id"])
        team_name = team["team_name"]
        try:
            avg_skill = int(round(float(team.get("avg_skill", 0))))
        except Exception:
            avg_skill = team.get("avg_skill", "—")
        wins      = int(team.get("wins", 0))
        losses    = int(team.get("losses", 0))
        is_elim   = bool(team.get("is_eliminated", False))

        status_badge = "❌ Eliminated" if is_elim else "✅ Active"
        with st.expander(f"**{team_name}**  ·  Avg Skill {avg_skill}  ·  W {wins} / L {losses}  ·  {status_badge}", expanded=True):
            # Players in this team
            team_players = get_team_players(team_id)
            if not team_players.empty:
                cols = st.columns(2)
                for idx, (_, p) in enumerate(team_players.iterrows()):
                    cols[idx % 2].metric(
                        label=f"Player {idx + 1}",
                        value=p["name"],
                        delta=f"Skill {int(float(p.get('skill_rating', 0)))}",
                    )
            else:
                st.caption("No players assigned.")

            # Rename form (admins may rename teams even after schedule is generated)
            if auth.is_admin():
                with st.form(f"rename_{team_id}", clear_on_submit=True):
                    new_name = st.text_input("Rename team", value=team_name, max_chars=40, key=f"rename_input_{team_id}")
                    if st.form_submit_button("💾 Save Name"):
                        try:
                            rename_team(team_id, new_name)
                            st.success(f"Renamed to **{new_name}**.")
                            st.rerun()
                        except (ValueError, RuntimeError) as e:
                            st.error(str(e))
            else:
                st.caption("Unlock admin to rename teams.")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Reset — always visible; cascades to wipe schedule too
    # ---------------------------------------------------------------------------
    with st.expander("⚠️ Reset Teams"):
        if matches_exist:
            st.warning(
                "A schedule has been generated. **Resetting teams will also delete "
                "all match records and award data.** Player registrations are kept."
            )
        else:
            st.warning("This will wipe all teams and clear player assignments. Player list is kept.")
        if auth.is_admin():
            if st.button("🔄 Reset Teams" + (" & Schedule" if matches_exist else ""), type="secondary"):
                try:
                    reset_teams()
                    st.success("Teams (and schedule) reset. Head to Players to adjust the list, then rebuild.")
                    st.session_state.pop("proposed_pairs", None)
                    st.session_state.pop("proposed_pairs_players", None)
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
        else:
            st.caption("Unlock admin to reset teams.")

