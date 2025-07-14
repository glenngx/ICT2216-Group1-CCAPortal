from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from email_service import email_service
import bcrypt
import requests
import hashlib
import re
import pyotp
from functools import wraps
from application.captcha_utils import captcha_is_valid   # top of file
import os 
from application.models import User, Student, CCAMembers, db
import bcrypt
from application.auth_utils import log_login_attempt

def validate_password_nist(password):
    """
    Validate password according to NIST SP 800-63B guidelines
    """
    errors = []
    
    # Length requirements 
    if len(password) < 15:
        errors.append("Password must be at least 15 characters long")
    
    if len(password) > 64:
        errors.append("Password must not exceed 64 characters")
    
    # Check for all whitespace 
    if password.isspace():
        errors.append("Password cannot be only whitespace")
    
    # Check against compromised passwords 
    if is_compromised_password(password):
        errors.append("This password has been found in data breaches. Please choose a different password")
    
    return len(errors) == 0, errors

def is_compromised_password(password):
    """
    Check password against Have I Been Pwned API 
    """
    try:
        # Hash the password
        sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
        prefix = sha1_hash[:5]
        suffix = sha1_hash[5:]
        
        # Query Have I Been Pwned API
        url = f"https://api.pwnedpasswords.com/range/{prefix}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            # Check if suffix appears in results
            for line in response.text.splitlines():
                if line.startswith(suffix):
                    # Password found in breach data
                    return True
        
        return False
    except:
        # If API is down, allow password 
        return False

# Blueprint for misc routes
misc_bp = Blueprint('misc_routes', __name__)

def register_misc_routes(app, get_db_connection, login_required, validate_email, validate_student_id):
    # \*\ Added for MFA
    @misc_bp.route('/mfa-verify', methods=['GET', 'POST'])
    def mfa_verify():
        if os.getenv("TESTING") == "1":
            session['mfa_authenticated'] = True
            return redirect(url_for("student_routes.dashboard"))
    
        if 'user_id' not in session:
            return redirect(url_for('misc_routes.login'))
        
        if os.getenv("TESTING") == "1":
            session['mfa_authenticated'] = True
            return "MFA bypassed (test mode)"

        user = User.query.filter_by(UserId=session['user_id']).first()
        # Fetches the user by id to get the MFA secret.

        if not user or not user.MFATOTPSecret:
            # no secret yet → first-time flow
            return redirect(url_for('student_routes.mfa_setup'))

        totp = pyotp.TOTP(user.MFATOTPSecret)

        if request.method == 'POST':
            code = request.form.get('mfa_code', '').strip()
            if totp.verify(code):
                session['mfa_authenticated'] = True
                flash("MFA verified.", "success")
                return redirect(url_for('student_routes.dashboard'))
            else:
                flash("Invalid code.", "error")

        return render_template('mfa_verify.html')

    # \*\ END for MFA
    
    def authenticate_user(username, password):
        # ── ADMIN SPECIAL-CASE ─────────────────────────────────────────────
        # Replaces: SELECT ud.UserId, ud.Username, ud.Password, ud.SystemRole FROM [dbo].[UserDetails] AS ud WHERE ud.[SystemRole] = 'admin' AND ud.[Username] = ?
        admin_user = User.query.filter_by(SystemRole='admin', Username=username).first()
        if admin_user and bcrypt.checkpw(password.encode('utf-8'), admin_user.Password.encode('utf-8')):
            return {
                'user_id': admin_user.UserId,
                'student_id': admin_user.Username, # Admin has username as student_id in old code
                'role': admin_user.SystemRole,
                'name': admin_user.Username,
                'email': admin_user.Username # placeholder
            }

        user_details = None
        # Try email login
        # Replaces: SELECT ... FROM UserDetails ud INNER JOIN Student s ON ud.StudentId = s.StudentId WHERE s.Email = ?
        if validate_email(username):
            student = Student.query.filter_by(Email=username).first()
            if student:
                user_details = student.user_details
        # Try Student ID
        # Replaces: SELECT ... FROM UserDetails ud INNER JOIN Student s ON ud.StudentId = s.StudentId WHERE s.StudentId = ?
        elif validate_student_id(username):
            student = Student.query.filter_by(StudentId=int(username)).first()
            if student:
                user_details = student.user_details
        # Try username login
        # Replaces: SELECT ... FROM UserDetails ud INNER JOIN Student s ON ud.StudentId = s.StudentId WHERE ud.Username = ?
        else:
            user_details = User.query.filter_by(Username=username).first()

        # Check if user was found
        if not user_details:
            print(f"No user found with identifier: {username}")
            # \*\ Added for Logging
            log_login_attempt(username, None, success=False, reason="User not found")
           # \*\ Ended for Logging
            return None

        # SECURITY CHECK: Reject login if password is NULL (account not yet set up)
        stored_password = user_details.Password
        if stored_password is None:
            print(f"User {username} has no password set - login rejected, must use email link")
            return None

        # \*\ Edit for MFA
        # 🔒 Check if account is locked
        if hasattr(user_details, 'IsLocked') and user_details.IsLocked:
            # Auto-unlock logic
            last_failed = user_details.LastFailedLogin
            if last_failed and (datetime.utcnow() - last_failed > timedelta(minutes=30)):
                print(f"Auto-unlocking user {username} (30 minutes passed)")
                user_details.IsLocked = False
                user_details.FailedLoginAttempts = 0
                db.session.commit()
            else:
                print(f"User {username} is locked out due to too many failed login attempts.")
                # \*\ Added for logging
                log_login_attempt(username, user_details.UserId, success=False, reason="Account locked")
                # \*\ Added for logging
                return None
        # \*\ End for MFA

        # Remove TEMP_ prefix if present before bcrypt check
        password_to_check = stored_password
        if stored_password.startswith("TEMP_"):
            password_to_check = stored_password.replace("TEMP_", "", 1)

        try:
            # Verify password using bcrypt
            if bcrypt.checkpw(password.encode('utf-8'), password_to_check.encode('utf-8')):
                
                # \*\ Added for logging
                log_login_attempt(username, user_details.UserId, success=True, reason="Login success")
               # \*\ Ended for logging

                # \*\ Edited for Password Expiration
                if user_details.PasswordLastSet and (datetime.utcnow() - user_details.PasswordLastSet).days > 365:
                    flash("Your password has expired. Please reset it to continue.", "warning")
                    session['force_password_change'] = True
                    return None
                # \*\ End for Password Expiration
                
                # \*\ Edited for Failed login attempt
                user_details.FailedLoginAttempts = 0
                user_details.IsLocked = False
                db.session.commit()
               # \*\ End for Failed login attempt
                
                # ── PROMOTE TO MODERATOR IF NEEDED ─────────────────────────
                # Replaces: SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCARole = 'moderator'
                is_moderator = CCAMembers.query.filter_by(UserId=user_details.UserId, CCARole='moderator').first()
                promoted_role = 'moderator' if is_moderator else user_details.SystemRole

                return {
                    'user_id': user_details.UserId,
                    'student_id': user_details.StudentId,
                    'role': promoted_role,
                    'name': user_details.student.Name,
                    'email': user_details.student.Email,
                }
            else:
                # ❌ Wrong password: increment failure counter
                user_details.FailedLoginAttempts = (user_details.FailedLoginAttempts or 0) + 1
                user_details.LastFailedLogin = datetime.utcnow()

                # \*\ Edit for Failed login attempt
                if user_details.FailedLoginAttempts >= 5:
                    user_details.IsLocked = True
                    print(f"User {username} account locked after 5 failed attempts.")
               # \*\ End for Failed login attempt
                db.session.commit()
                # \*\ Added for logging
                log_login_attempt(username, user_details.UserId, success=False, reason="Wrong password")
                # \*\ Ended for logging
                print("Password verification failed")
                return None
        except Exception as bcrypt_error:
            print(f"Bcrypt error: {bcrypt_error}")
            return None

    @misc_bp.route('/')
    def index():
        if 'user_id' in session and os.getenv("TESTING") != "1":
            # Assuming 'dashboard' route is in 'student_routes' blueprint
            return redirect(url_for('student_routes.dashboard'))
        return redirect(url_for('misc_routes.login'))

    @misc_bp.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user_id' in session:
            if os.getenv("TESTING") != "1":
                return redirect(url_for('student_routes.dashboard'))
        
        if request.method == 'POST':
            # Clear session to prevent session fixation
            session.clear()

            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            # This block to prevent buffer overflow
            if len(username) > 100 or len(password) > 100:
                flash("Input too long. Please shorten your username or password.", "error")
                return render_template(
                    "login.html",
                    RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY")
                )
            
            # \*\ Added for Captcha
            captcha_token = request.form.get('g-recaptcha-response', '')

            if not captcha_is_valid(captcha_token, request.remote_addr):
                flash("CAPTCHA verification failed. Please try again.", "error")
            # IMPORTANT: pass the site key when re-rendering
                return render_template(
                "login.html",
                RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY")
                )
            # \*\ Ended for Captcha

            if not username or not password:
                flash('Please enter both username and password.', 'error')
                #return render_template('login.html')
                # \*\ Started for Captcha
                return render_template('login.html',
                       RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY"))
                # \*\ Ended for Captcha
                
            user = authenticate_user(username, password)
            # \*\ Edit for MFA
            # 🔒 If user is locked, show message
            locked_user = User.query.filter_by(Username=username).first()
            if locked_user and locked_user.IsLocked:
                remaining_minutes = None
                if locked_user.LastFailedLogin:
                    elapsed = datetime.utcnow() - locked_user.LastFailedLogin
                    if elapsed < timedelta(minutes=30):
                        remaining = timedelta(minutes=30) - elapsed
                        remaining_minutes = int(remaining.total_seconds() // 60) + 1  # Round up

                flash("Your account is locked due to too many failed login attempts.", "error")
                return render_template(
                    'login.html',
                    RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY"),
                    lockout_remaining=remaining_minutes
                )
            # \*\ End for MFA
            
            if user:
                # Cookie expires when user close the browser 
                session.permanent = False

                session['user_id'] = user['user_id']
                session['student_id'] = user['student_id']
                session['role'] = user['role']
                session['name'] = user['name']
                session['email'] = user['email']
                session['login_time'] = datetime.now().isoformat()

                if os.getenv("TESTING") == "1":
                    session['mfa_authenticated'] = True
                    return redirect(url_for('student_routes.dashboard'))

                # \*\ Added for Password Expiration
                # 🔒 Enforce password reset if expired
                if session.pop('force_password_change', False):
                    return redirect(url_for('student_routes.change_password'))
                # \*\ Ended for Password Expiration

                # \*\ Added for MFA
                # Check if user has MFA enabled
                mfa_user = User.query.filter_by(UserId=user['user_id']).first()
                # Fetches user by id to check for an MFA secret.

                # clear any stale MFA flag
                session.pop('mfa_authenticated', None)

                if os.getenv("TESTING") == "1":
                    session['mfa_authenticated'] = True
                    return redirect(url_for('student_routes.dashboard'))

                # Check MFA requirement
                mfa_user = User.query.filter_by(UserId=user['user_id']).first()
                session.pop('mfa_authenticated', None)
                
                # MFA enforcement
                if mfa_user and mfa_user.MFATOTPSecret:
                    return redirect(url_for('misc_routes.mfa_verify'))
                elif not mfa_user or not mfa_user.MFATOTPSecret:
                    return redirect(url_for('student_routes.mfa_setup'))

            else:
                flash('Invalid username or password.', 'error')
                
                return render_template('login.html', testing=(os.getenv("TESTING") == "1"))
        
        return render_template('login.html', testing=(os.getenv("TESTING") == "1"))
    
    @misc_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        # Clear all other existing sessions
        session.clear()

        """Handle password reset with token from email"""
        # Verify the token
        token_data = email_service.verify_password_reset_token(token)
        
        if not token_data:
            flash('Invalid or expired password setup link. Please contact your administrator for a new link.', 'error')
            return redirect(url_for('misc_routes.login'))
        
        student_id = token_data.get('student_id')

        # Check if user has already used the link to reset their password
        user_for_reset = User.query.filter_by(StudentId=student_id).first()
        # Fetches user by student_id to check if password exists.
        if user_for_reset and user_for_reset.Password is not None:
            flash("This reset link has already been used. Redirecting to login page...", "error")
            return redirect(url_for('misc_routes.login'))
            
        if request.method == 'POST':
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validation
            if not new_password or not confirm_password:
                flash('Both password fields are required.', 'error')
                return render_template('reset_password.html', token=token)
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('reset_password.html', token=token)
            
            is_valid, errors = validate_password_nist(new_password)
            if not is_valid:
                for error in errors:
                    flash(error, 'error')
                return render_template('reset_password.html', token=token)
            try:
                # Get current password to check if it exists
                # cursor.execute("SELECT Password FROM UserDetails WHERE StudentId = ?", (student_id,))
                # current_password_row = cursor.fetchone()
                user_to_update = User.query.filter_by(StudentId=student_id).first()
                # Fetches user by student_id to update password.

                if not user_to_update:
                    flash('User account not found. Please contact support.', 'error')
                    return render_template('reset_password.html', token=token)
                
                current_password = user_to_update.Password
                
                # Check if they're trying to reuse the temporary password 
                if current_password and current_password.startswith('TEMP_'):
                    # Extract the original temporary password
                    original_hashed_temp = current_password.replace('TEMP_', '')
                    if bcrypt.checkpw(new_password.encode('utf-8'), original_hashed_temp.encode('utf-8')):
                        flash('You cannot use the temporary password. Please choose a different password.', 'error')
                        return render_template('reset_password.html', token=token)
                
                # Update password *\* added hashing
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                # cursor.execute("""
                #     UPDATE UserDetails 
                #     SET Password = ? 
                #     WHERE StudentId = ?
                # """, (hashed_password, student_id))
                user_to_update.Password = hashed_password
                #Update for \*\ password expiration
                user_to_update.PasswordLastSet = datetime.utcnow()
                #End for \*\ password expiration
                
                db.session.commit()
                # \*\ End Updates user password and commits the change.
                
                flash('Password set successfully! You can now log in to CCA Portal with your Student ID and new password.', 'success')
                return redirect(url_for('misc_routes.login'))
                
            except Exception as e:
                db.session.rollback()
                print(f"Password reset error: {e}")
                flash('Error setting password. Please try again.', 'error')
                return render_template('reset_password.html', token=token)
        
        # GET request - show the reset form
        # Get student details for display
        student_name = "Student"  # Default fallback
        student = Student.query.filter_by(StudentId=student_id).first()
        # Fetches student by id to display their name.
        if student:
            student_name = student.Name
        
        return render_template('reset_password.html', token=token, student_name=student_name)

    @misc_bp.route('/logout')
    @login_required
    def logout():
        name = session.get('name', 'User')
        # Clear session when logging out
        session.clear()
        flash(f'Goodbye, {name}! You have been logged out successfully.', 'success')
        return redirect(url_for('misc_routes.login'))

    app.register_blueprint(misc_bp)
