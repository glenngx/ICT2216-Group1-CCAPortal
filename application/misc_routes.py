from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from email_service import email_service
import bcrypt
import requests
import hashlib
import re
import pyotp
from functools import wraps


def validate_password_nist(password):
    """
    Validate password according to NIST SP 800-63B guidelines
    """
    errors = []
    
    # Length requirements 
    if len(password) < 15:
        errors.append("Password must be at least 15 characters long")
    
    if len(password) > 128:
        errors.append("Password must not exceed 128 characters")
    
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
        if 'user_id' not in session:
            return redirect(url_for('misc_routes.login'))

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MFATOTPSecret FROM UserDetails WHERE UserId = ?",
                (session['user_id'],)
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                # no secret yet → first-time flow
                return redirect(url_for('student_routes.mfa_setup'))

            totp = pyotp.TOTP(row[0])

            if request.method == 'POST':
                code = request.form.get('mfa_code', '').strip()
                if totp.verify(code):
                    session['mfa_authenticated'] = True
                    flash("MFA verified.", "success")
                    return redirect(url_for('student_routes.dashboard'))
                else:
                    flash("Invalid code.", "error")

            return render_template('mfa_verify.html')

        finally:
            conn.close()    # \*\ END for MFA
    
    # Authentication function (moved from app.py)
    def authenticate_user(username, password):
        conn = get_db_connection()
        if not conn:
            print("Database connection failed")
            return None
        
        try:
            cursor = conn.cursor()
            
            print(f"Attempting login with username: '{username}' and password: '{password}'")
            
            user = None  # Initialize user variable
            
            # Handle admin login specifically first
            if username == 'admin':  
                print("Admin login attempt...")
                query = """
                SELECT ud.UserId, ud.Username, ud.Password, ud.SystemRole
                FROM UserDetails ud
                WHERE ud.SystemRole = 'admin'
                """
                cursor.execute(query)
                admin_user = cursor.fetchone()
                print(f"Admin query result: {admin_user}")
                
                if admin_user and password == admin_user[2]: # Admin passwords are not hashed in the current setup
                    return {
                        'user_id': admin_user[0],
                        'student_id': admin_user[1], # Admin might not have a student ID in Student table
                        'role': admin_user[3],
                        'name': admin_user[1], # Use username as name for admin
                        'email': admin_user[1] # Placeholder, admin might not have an email in Student table
                    }
            
            # Try email login
            if validate_email(username):
                print("Validating as email...")
                query = """
                SELECT ud.UserId, ud.StudentId, ud.Password, ud.SystemRole, s.Name, s.Email
                FROM UserDetails ud
                INNER JOIN Student s ON ud.StudentId = s.StudentId
                WHERE s.Email = ?
                """
                cursor.execute(query, (username,))
                user = cursor.fetchone()
                print(f"Email query result: {user}")
                
            # Try Student ID
            elif validate_student_id(username):
                print("Validating as Student ID...")
                query = """
                SELECT ud.UserId, ud.StudentId, ud.Password, ud.SystemRole, s.Name, s.Email
                FROM UserDetails ud
                INNER JOIN Student s ON ud.StudentId = s.StudentId
                WHERE s.StudentId = ?
                """
                cursor.execute(query, (int(username),)) # Ensure username is cast to int for StudentId
                user = cursor.fetchone()
                print(f"StudentID query result: {user}")
                
            else:
                # Try username login 
                print("Validating as username...")
                query = """
                SELECT ud.UserId, ud.StudentId, ud.Password, ud.SystemRole, s.Name, s.Email
                FROM UserDetails ud
                INNER JOIN Student s ON ud.StudentId = s.StudentId
                WHERE ud.Username = ?
                """
                cursor.execute(query, (username,))
                user = cursor.fetchone()
                print(f"Username query result: {user}")
            
            # Check if user was found
            if not user:
                print(f"No user found with identifier: {username}")
                return None
            
            # Extract password from the result
            stored_password = user[2]  # Password from UserDetails
            print(f"Stored password: '{stored_password}', Entered password: '{password}'")
            
            # SECURITY CHECK: Reject login if password is NULL (account not yet set up)
            if stored_password is None:
                print(f"User {username} has no password set - login rejected, must use email link")
                return None
            
            # Remove TEMP_ prefix if present before bcrypt check
            password_to_check = stored_password
            if stored_password.startswith("TEMP_"):
                password_to_check = stored_password.replace("TEMP_", "", 1)
            
            # Verify password using bcrypt
            try:
                if bcrypt.checkpw(password.encode('utf-8'), password_to_check.encode('utf-8')):
                    return {
                        'user_id': user[0],     # UserId
                        'student_id': user[1],  # StudentId from UserDetails
                        'role': user[3],        # SystemRole
                        'name': user[4],        # Name from Student table
                        'email': user[5],       # Email from Student table
                    }
                else:
                    print("Password verification failed")
                    return None
            except Exception as bcrypt_error:
                print(f"Bcrypt error: {bcrypt_error}")
                return None
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return None
        finally:
            if conn:
                conn.close()

    @misc_bp.route('/')
    def index():
        if 'user_id' in session:
            # Assuming 'dashboard' route is in 'student_routes' blueprint
            return redirect(url_for('student_routes.dashboard'))
        return redirect(url_for('misc_routes.login'))

    @misc_bp.route('/login', methods=['GET', 'POST'])
    def login():
        if 'user_id' in session:
            return redirect(url_for('student_routes.dashboard'))
        
        if request.method == 'POST':
            # Clear session to prevent session fixation
            session.clear()

            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Please enter both username and password.', 'error')
                return render_template('login.html')
            
            user = authenticate_user(username, password)
            
            if user:
                # Cookie expires when user close the browser 
                session.permanent = False

                session['user_id'] = user['user_id']
                session['student_id'] = user['student_id']
                session['role'] = user['role']
                session['name'] = user['name']
                session['email'] = user['email']
                session['login_time'] = datetime.now().isoformat()

                # \*\ Added for MFA
                # Check if user has MFA enabled
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT MFATOTPSecret FROM UserDetails WHERE UserId = ?", (user['user_id'],))
                row = cursor.fetchone()
                conn.close()

            # clear any stale MFA flag
                session.pop('mfa_authenticated', None)

                if row and row[0]:
                    # secret already exists → ask for 6-digit code
                    return redirect(url_for('misc_routes.mfa_verify'))
                else:
                    # first login → force setup
                    return redirect(url_for('student_routes.mfa_setup'))

                # \*\ Ended for MFA

            else:
                flash('Invalid username or password.', 'error')
                
                return render_template('login.html')
        
        return render_template('login.html')
    
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
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT Password FROM UserDetails WHERE StudentId = ?", (student_id,))
                row = cursor.fetchone()

                if row and row[0] is not None:
                    flash("This reset link has already been used. Redirecting to login page...", "error")
                    return redirect(url_for('misc_routes.login'))

            except Exception as e:
                print(f"Password Reset Link Error: {e}")
                flash("There was an error validating your password reset link.", "error")
                return redirect(url_for('misc_routes.login'))
            finally:
                conn.close()
            
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
            
            conn = get_db_connection()
            if not conn:
                flash('Database connection error.', 'error')
                return render_template('reset_password.html', token=token)
            
            try:
                cursor = conn.cursor()
                
                # Get current password to check if it exists
                cursor.execute("SELECT Password FROM UserDetails WHERE StudentId = ?", (student_id,))
                current_password_row = cursor.fetchone()
                
                if not current_password_row:
                    flash('User account not found. Please contact support.', 'error')
                    return render_template('reset_password.html', token=token)
                
                current_password = current_password_row[0]
                
                # Check if they're trying to reuse the temporary password 
                if current_password and current_password.startswith('TEMP_'):
                    # Extract the original temporary password
                    original_hashed_temp = current_password.replace('TEMP_', '')
                    if bcrypt.checkpw(new_password.encode('utf-8'), original_hashed_temp.encode('utf-8')):
                        flash('You cannot use the temporary password. Please choose a different password.', 'error')
                        return render_template('reset_password.html', token=token)
                
                # Update password *\* added hashing
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute("""
                    UPDATE UserDetails 
                    SET Password = ? 
                    WHERE StudentId = ?
                """, (hashed_password, student_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    flash('Password set successfully! You can now log in to CCA Portal with your Student ID and new password.', 'success')
                    return redirect(url_for('misc_routes.login'))
                else:
                    flash('User not found. Please contact support.', 'error')
                    return render_template('reset_password.html', token=token)
                
            except Exception as e:
                conn.rollback()
                print(f"Password reset error: {e}")
                flash('Error setting password. Please try again.', 'error')
                return render_template('reset_password.html', token=token)
            finally:
                if conn:
                    conn.close()
        
        # GET request - show the reset form
        # Get student details for display
        conn = get_db_connection()
        student_name = "Student"  # Default fallback
        
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT Name FROM Student WHERE StudentId = ?", (student_id,))
                name_row = cursor.fetchone()
                if name_row:
                    student_name = name_row[0]
            except:
                pass  # Use default name
            finally:
                conn.close()
        
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