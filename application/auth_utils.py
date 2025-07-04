# application/auth_utils.py
from functools import wraps
from flask import session, redirect, url_for, flash
from application.models import db, User, CCAMembers

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
            flash("Access denied.", "error")
            return redirect(url_for("student_routes.dashboard"))

        mfa_redirect = _mfa_guard()  # MFA check
        if mfa_redirect:
            return mfa_redirect

        try:
            # Check if user is an admin
            is_admin = db.session.query(User).filter_by(
                UserId=session["user_id"],
                SystemRole="admin"
            ).first() is not None

            if not is_admin:
                flash("Access denied.", "error")
                print(f'DEBUG: admin access denied')
                return redirect(url_for("student_routes.dashboard"))

        except Exception as e:
            print(f"[admin_required DB check error] {e}")
            flash("Error verifying privileges.", "error")
            return redirect(url_for("student_routes.dashboard"))

        return f(*args, **kwargs)
    return decorated



# ───────────────────────────────────────────────────────────
def moderator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("misc_routes.login"))
        
        if session.get("role") not in ("moderator"):
            flash("Access denied.", "error")
            return redirect(url_for("student_routes.dashboard"))
        
        mfa_redirect = _mfa_guard()          # ← MFA check added
        if mfa_redirect:
            return mfa_redirect
        
        try:
            # Check if user is a moderator in any CCA
            is_moderator = db.session.query(CCAMembers).filter_by(
                UserId=session['user_id'],
                CCARole='moderator'
            ).first() is not None

            if not is_moderator:
                flash("Access denied.", "error")
                print(f'DEBUG: moderator access denied.')
                return redirect(url_for("student_routes.dashboard"))

        except Exception as e:
            print(f"[moderator_required DB check error] {e}")
            flash("Error verifying moderator role.", "error")
            return redirect(url_for("student_routes.dashboard"))
        
        return f(*args, **kwargs)
    return decorated
