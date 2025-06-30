# application/auth_utils.py
from functools import wraps
from flask import session, redirect, url_for

def login_required_with_mfa(f):
    """
    Decorator: user must be logged in AND have completed MFA this session.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("misc_routes.login"))
        if not session.get("mfa_authenticated"):
            return redirect(url_for("misc_routes.mfa_verify"))
        return f(*args, **kwargs)
    return decorated
