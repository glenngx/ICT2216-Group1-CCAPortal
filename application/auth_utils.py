# application/auth_utils.py
from functools import wraps
from flask import session, redirect, url_for, flash

# ───────────────────────────────────────────────────────────
def _mfa_guard():
    """Redirect to /mfa-verify if this session skipped MFA."""
    if not session.get("mfa_authenticated"):
        flash("Please complete MFA verification first.", "warning")
        return redirect(url_for("misc_routes.mfa_verify"))

# ───────────────────────────────────────────────────────────
def login_required_with_mfa(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("misc_routes.login"))
        mfa_redirect = _mfa_guard()
        if mfa_redirect:
            return mfa_redirect
        return f(*args, **kwargs)
    return decorated

# ───────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("misc_routes.login"))
        if session.get("role") != "admin":
            flash("Admin access only.", "error")
            return redirect(url_for("student_routes.dashboard"))
        mfa_redirect = _mfa_guard()          # ← MFA check added
        if mfa_redirect:
            return mfa_redirect
        return f(*args, **kwargs)
    return decorated

# ───────────────────────────────────────────────────────────
def moderator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("misc_routes.login"))
        if session.get("role") not in ("moderator", "admin"):
            flash("Moderator access only.", "error")
            return redirect(url_for("student_routes.dashboard"))
        mfa_redirect = _mfa_guard()          # ← MFA check added
        if mfa_redirect:
            return mfa_redirect
        return f(*args, **kwargs)
    return decorated
