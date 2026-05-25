"""
github_sync.py
--------------
GitHub API helpers for persisting CSV data files back to the repository.

Reads credentials from st.secrets:
  GITHUB_TOKEN        — personal access token (repo scope)
  GITHUB_REPO         — "owner/repo-name"  e.g. "Abhinav-ECI/Carrom-Tournament"
  GITHUB_DATA_BRANCH  — branch to commit to (default: "main")

When running locally without secrets configured, every call is a no-op so
the app still works using only the local filesystem.
"""

from __future__ import annotations

import streamlit as st


def _is_configured() -> bool:
    try:
        _ = st.secrets["GITHUB_TOKEN"]
        _ = st.secrets["GITHUB_REPO"]
        return True
    except (KeyError, FileNotFoundError):
        return False


def _get_repo():
    from github import Github
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(st.secrets["GITHUB_REPO"])


def push_file(repo_path: str, content: str, message: str = "Update tournament data") -> None:
    """Commit or update *repo_path* in the GitHub repo with *content*.

    - Creates the file if it doesn't exist yet.
    - Skips the commit if the content hasn't changed.
    - Silently no-ops when secrets are not configured (local dev mode).
    """
    if not _is_configured():
        return

    from github import GithubException, UnknownObjectException
    branch = st.secrets.get("GITHUB_DATA_BRANCH", "main")
    try:
        repo = _get_repo()
        try:
            existing = repo.get_contents(repo_path, ref=branch)
            if existing.decoded_content.decode("utf-8") == content:
                return  # no change — skip commit
            repo.update_file(repo_path, message, content, existing.sha, branch=branch)
        except UnknownObjectException:
            repo.create_file(repo_path, message, content, branch=branch)
    except GithubException:
        raise  # let the caller (sync_to_github) handle and re-queue


def pull_file(repo_path: str) -> str | None:
    """Fetch the raw content of *repo_path* from GitHub.

    Returns ``None`` when secrets are not configured or the file doesn't exist.
    """
    if not _is_configured():
        return None

    from github import GithubException, UnknownObjectException
    branch = st.secrets.get("GITHUB_DATA_BRANCH", "main")
    try:
        repo = _get_repo()
        contents = repo.get_contents(repo_path, ref=branch)
        return contents.decoded_content.decode("utf-8")
    except UnknownObjectException:
        return None  # file doesn't exist yet — expected on first run
    except GithubException as e:
        try:
            st.warning(f"⚠️ GitHub pull failed: {e}")
        except Exception:
            pass
        return None
