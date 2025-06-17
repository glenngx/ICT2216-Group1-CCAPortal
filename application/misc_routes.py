from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime

# Blueprint for misc routes
misc_bp = Blueprint('misc_routes', __name__)

def register_misc_routes(app, get_db_connection, login_required, validate_email, validate_student_id):
    # Authentication function (moved from app.py)
    def authenticate_user(username, password):
        conn = get_db_connection()
        if not conn:
            print("Database connection failed")
            return None
        
        try:
            cursor = conn.cursor()
            
            print(f"Attempting login with username: '{username}' and password: '{password}'")
            
            query = """
            SELECT ud.UserId, ud.StudentId, ud.Password, ud.SystemRole
            FROM UserDetails ud
            WHERE ud.Username = ? OR ud.StudentId = ?
            """
            cursor.execute(query, (username, username))
            user_record = cursor.fetchone()
            
            if not user_record:
                print(f"No user found with username: {username}")
                return None
            
            # Handle admin login specifically
            if user_record[3] == 'admin':
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
            
            # Try email
            elif validate_email(username):
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
                # Fallback to username if not email or student_id format, or if initial query found a user by username
                # This part handles the case where username is neither email nor student_id but a direct username match
                if user_record: # user_record was fetched using username or student_id
                    # We need to fetch Name and Email from Student table if it's not an admin
                    if user_record[3] != 'admin':
                        student_id_from_record = user_record[1]
                        query_student_details = """
                        SELECT s.Name, s.Email
                        FROM Student s
                        WHERE s.StudentId = ?
                        """
                        cursor.execute(query_student_details, (student_id_from_record,))
                        student_details = cursor.fetchone()
                        if student_details:
                             user = user_record + student_details # Combine records
                        else: # Should not happen if DB is consistent
                            print(f"Student details not found for StudentId: {student_id_from_record}")
                            user = None
                    else: # Admin already handled
                        user = None # Should not reach here if admin was processed correctly
                else:
                    print(f"Invalid username format or no initial match: {username}")
                    return None
            
            # Check regular user authentication
            if 'user' in locals() and user: # Ensure 'user' is defined
                stored_password = user[2] # Password from UserDetails
                print(f"Stored password: '{stored_password}', Entered password: '{password}'")
                
                # Assuming non-admin passwords are not hashed for now, based on original logic
                if password == stored_password:
                    return {
                        'user_id': user[0],    # UserId
                        'student_id': user[1], # StudentId from UserDetails
                        'role': user[3],       # SystemRole
                        'name': user[4],       # Name from Student table
                        'email': user[5]       # Email from Student table
                    }
            
            print("Authentication failed - no matching user or wrong password")
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
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Please enter both username and password.', 'error')
                return render_template('login.html')
            
            user = authenticate_user(username, password)
            
            if user:
                session.permanent = True
                session['user_id'] = user['user_id']
                session['student_id'] = user['student_id']
                session['role'] = user['role']
                session['name'] = user['name']
                session['email'] = user['email']
                session['login_time'] = datetime.now().isoformat()
                
                flash(f'Welcome back, {user["name"]}!', 'success')
                # Redirect to student dashboard, which will handle admin redirection
                return redirect(url_for('student_routes.dashboard'))
            else:
                flash('Invalid username or password.', 'error')
                return render_template('login.html')
        
        return render_template('login.html')

    @misc_bp.route('/logout')
    @login_required
    def logout():
        name = session.get('name', 'User')
        session.clear()
        flash(f'Goodbye, {name}! You have been logged out successfully.', 'success')
        return redirect(url_for('misc_routes.login'))

    app.register_blueprint(misc_bp)
