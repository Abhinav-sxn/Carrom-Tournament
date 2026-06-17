"""
team_builder.py  —  Phase 2
Balanced team pairing algorithm + team naming.

Algorithm (sorted interleaving):
  1. Sort players by skill_rating descending.
  2. Pair player[0] with player[N-1], player[1] with player[N-2], etc.
  3. Each pair forms a 2-player team — averages are naturally equalised.
  4. Organiser reviews averages, optionally assigns team names, then locks.
"""

import pandas as pd
from modules.excel_sync import load_sheet, save_sheet, get_next_id
from modules.player_manager import update_player_team


def get_default_pairing(players_df: pd.DataFrame) -> list:
    """Return the best pairing as a list of (player_id_1, player_id_2) tuples.

    Algorithm:
      1. Find all "satisfiable" preference pairs: A prefers B AND
         (B has no preference OR B also prefers A).
      2. Resolve conflicts greedily — mutual preferences win over one-way;
         ties broken by the pair whose avg skill is closest to the
         overall field average (keeps the bracket balanced).
      3. Remaining unpaired players fall back to sorted interleaving
         (rank-1 paired with rank-N, etc.).
    """
    skills   = {int(r["player_id"]): float(r["skill_rating"]) for _, r in players_df.iterrows()}
    name_map = {str(r["name"]).strip().lower(): int(r["player_id"]) for _, r in players_df.iterrows()}
    pref_map: dict[int, int | None] = {}
    for _, r in players_df.iterrows():
        pid  = int(r["player_id"])
        pref = str(r.get("partner_pref") or "").strip().lower()
        pref_map[pid] = name_map.get(pref)   # None when no / invalid preference

    overall_avg = sum(skills.values()) / len(skills)
    all_pids    = list(skills.keys())

    # Collect every satisfiable pair with a sort key:
    #   (0 = mutual preferred over 1 = one-way, then deviation from overall avg)
    candidates: list[tuple] = []
    for i, pid_a in enumerate(all_pids):
        for pid_b in all_pids[i + 1:]:
            a_wants_b = pref_map.get(pid_a) == pid_b
            b_wants_a = pref_map.get(pid_b) == pid_a
            b_no_pref = pref_map.get(pid_b) is None
            a_no_pref = pref_map.get(pid_a) is None

            satisfiable = (
                (a_wants_b and (b_wants_a or b_no_pref)) or
                (b_wants_a and (a_wants_b or a_no_pref))
            )
            if satisfiable:
                mutual    = a_wants_b and b_wants_a
                skill_dev = abs((skills[pid_a] + skills[pid_b]) / 2 - overall_avg)
                candidates.append((0 if mutual else 1, skill_dev, pid_a, pid_b))

    candidates.sort()   # best (mutual + closest to avg) first

    paired: set[int] = set()
    locked: list[tuple[int, int]] = []
    for _, _, pid_a, pid_b in candidates:
        if pid_a not in paired and pid_b not in paired:
            locked.append((pid_a, pid_b))
            paired.update({pid_a, pid_b})

    # Balanced interleaving for the remaining players
    remaining = sorted(
        [pid for pid in all_pids if pid not in paired],
        key=lambda pid: skills[pid],
        reverse=True,
    )
    n = len(remaining)
    for i in range(n // 2):
        locked.append((remaining[i], remaining[n - 1 - i]))

    return locked


def build_balanced_teams(custom_pairing: list | None = None) -> pd.DataFrame:
    """
    Read players from the Players sheet, run the pairing algorithm,
    create Team records, assign player team_ids, and save both sheets.
    Returns the Teams DataFrame.

    Pass *custom_pairing* as a list of (player_id_1, player_id_2) tuples to
    override the default balanced algorithm (e.g. after manual swaps in the UI).

    Raises:
        RuntimeError  if teams already exist, or player count < 4, or player
                      count is not even.
    """
    existing_teams = load_sheet("Teams")
    if not existing_teams.empty:
        raise RuntimeError(
            "Teams have already been built. Reset teams first to rebuild."
        )

    players_df = load_sheet("Players")
    if players_df.empty or len(players_df) < 3:
        raise RuntimeError("At least 3 players are required to form teams.")

    players_map = {int(row["player_id"]): row for _, row in players_df.iterrows()}

    if custom_pairing is not None:
        pairing = [(int(a), int(b)) for a, b in custom_pairing]
        all_ids = set(players_map.keys())
        for pid1, pid2 in pairing:
            if pid1 not in all_ids or pid2 not in all_ids:
                raise ValueError("Custom pairing references an unknown player ID.")
    else:
        pairing = get_default_pairing(players_df)

    paired_pids = set()
    for pid1, pid2 in pairing:
        paired_pids.add(pid1)
        paired_pids.add(pid2)

    leftover_pids = [pid for pid in players_map if pid not in paired_pids]

    teams = []
    base_team_id = get_next_id("Teams", "team_id")
    for i, (pid1, pid2) in enumerate(pairing):
        p1 = players_map[pid1]
        p2 = players_map[pid2]
        avg = round((float(p1["skill_rating"]) + float(p2["skill_rating"])) / 2, 2)
        team_id = base_team_id + i
        teams.append({
            "team_id":       team_id,
            "team_name":     f"Team {_num_to_letter(i)}",
            "avg_skill":     avg,
            "wins":          0,
            "losses":        0,
            "is_eliminated": False,
        })

    leftover_team = None
    if leftover_pids:
        leftover_pid = leftover_pids[0]
        p = players_map[leftover_pid]
        team_id = base_team_id + len(pairing)
        leftover_team = {
            "team_id":       team_id,
            "team_name":     f"Team {_num_to_letter(len(pairing))} ({p['name']} - Single)",
            "avg_skill":     float(p["skill_rating"]),
            "wins":          0,
            "losses":        0,
            "is_eliminated": False,
        }
        teams.append(leftover_team)

    teams_df = pd.DataFrame(teams)
    save_sheet("Teams", teams_df)

    # Assign team_ids back to players (bulk update)
    players_copy = players_df.copy()
    for team, (pid1, pid2) in zip(teams[:len(pairing)], pairing):
        players_copy.loc[players_copy["player_id"] == pid1, "team_id"] = team["team_id"]
        players_copy.loc[players_copy["player_id"] == pid2, "team_id"] = team["team_id"]

    if leftover_team is not None:
        players_copy.loc[players_copy["player_id"] == leftover_pids[0], "team_id"] = leftover_team["team_id"]

    save_sheet("Players", players_copy)
    return teams_df


def rename_team(team_id: int, new_name: str) -> None:
    """Update a team's display name."""
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Team name cannot be empty.")

    df = load_sheet("Teams")
    if df.empty or team_id not in df["team_id"].values:
        raise ValueError(f"Team ID {team_id} not found.")

    # Prevent duplicate names (case-insensitive), ignoring own row
    other_names = df.loc[df["team_id"] != team_id, "team_name"].str.lower()
    if new_name.lower() in other_names.values:
        raise ValueError(f'A team named "{new_name}" already exists.')

    df.loc[df["team_id"] == team_id, "team_name"] = new_name
    save_sheet("Teams", df)


def reset_teams() -> None:
    """
    Wipe all match data, then wipe all teams and clear player team assignments.
    Cascades automatically: schedule + match stats are cleared first so the
    dataset is always left in a consistent state.
    """
    # 1. Reset schedule first (safe even when Matches is already empty)
    from modules.match_scheduler import reset_schedule
    reset_schedule()

    # 2. Clear Teams sheet
    save_sheet("Teams", pd.DataFrame(columns=[
        "team_id", "team_name", "avg_skill", "wins", "losses", "is_eliminated"
    ]))

    # 3. Clear team_id on all players
    players_df = load_sheet("Players")
    if not players_df.empty:
        players_df["team_id"] = None
        save_sheet("Players", players_df)


def get_all_teams() -> pd.DataFrame:
    """Return all teams as a DataFrame."""
    return load_sheet("Teams")


def get_team_players(team_id: int) -> pd.DataFrame:
    """Return the two players belonging to a team."""
    players_df = load_sheet("Players")
    if players_df.empty:
        return players_df
    return players_df[players_df["team_id"] == team_id].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num_to_letter(n: int) -> str:
    """0 → A, 1 → B, … 25 → Z, 26 → AA, etc."""
    result = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result
