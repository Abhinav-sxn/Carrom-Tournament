"""
auth.py
-------
Very small admin-auth helper for the Streamlit app.

- Uses a single admin password hash stored in `st.secrets["ADMIN_PASSWORD_HASH"]`.
- Adds a reusable sidebar widget to login/logout and exposes `is_admin()`.

This is intentionally simple: if you want per-user identities, use GitHub OAuth
or an external auth provider and check `st.session_state` similarly.
"""

from __future__ import annotations

import hashlib

try:
    import streamlit as st
except Exception:  # pragma: no cover - import-time when not running in Streamlit
    st = None


def _check_password(password: str) -> bool:
    if st is None:
        return False
    stored = st.secrets.get("ADMIN_PASSWORD_HASH")
    if not stored:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == stored


def is_admin() -> bool:
    if st is None:
        return False
    return bool(st.session_state.get("is_admin", False))


def admin_widget() -> None:
    """Render a small login widget in the sidebar to toggle admin mode.

    Stores the boolean `is_admin` in `st.session_state` on success.
    """
    if st is None:
        return

    # Show current state
    if is_admin():
        st.sidebar.success("Admin mode")
        if st.sidebar.button("Log out", key="admin_logout"):
            st.session_state["is_admin"] = False
            st.experimental_rerun()
        return

    # Use a form so the password value is submitted atomically with the
    # unlock action. This avoids racey behavior where the button click
    # might not carry the latest text_input value on the first click.
    submitted = False
    with st.sidebar.form("admin_form", clear_on_submit=True):
        pw = st.text_input("Admin password", type="password", key="_admin_pw_input")
        submitted = st.form_submit_button("Unlock admin", key="admin_unlock")

    if submitted:
        if _check_password(pw):
            st.session_state["is_admin"] = True
            st.experimental_rerun()
        else:
            st.sidebar.error("Invalid password")
