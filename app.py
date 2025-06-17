from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyodbc
import bcrypt
from functools import wraps
import re
from datetime import datetime, timedelta
try:
    from config import DB_CONNECTION_STRING, SECRET_KEY
    print("Configuration loaded from config.py")
except ImportError:
    print("ERROR: config.py file not found!")
    exit(1)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Timeout after 30 min of inactivity
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30) 

# Database connection function
def get_db_connection():
    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        return conn
    except pyodbc.Error as e:
        print(f"Database connection error: {e}")
        return None

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        if session.get('role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

# Moderator required decorator
def moderator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        
        # Check if user is a moderator in any CCA
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('dashboard'))
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied. Moderator privileges required.', 'error')
                return redirect(url_for('dashboard'))
            
        except Exception as e:
            print(f"Moderator check error: {e}")
            flash('Error checking permissions.', 'error')
            return redirect(url_for('dashboard'))
        finally:
            conn.close()
        
        return f(*args, **kwargs)
    return decorated_function

# Input validation functions
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    result = re.match(pattern, email) is not None
    print(f"Email validation for '{email}': {result}")
    return result

def validate_student_id(student_id):
    # Assuming student ID is numeric and 7 digits
    result = student_id.isdigit() and len(student_id) == 7
    print(f"Student ID validation for '{student_id}': {result}")
    return result

# Authentication function
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
            
            if admin_user and password == admin_user[2]:
                return {
                    'user_id': admin_user[0],
                    'student_id': admin_user[1],
                    'role': admin_user[3],
                    'name': admin_user[1],
                    'email': admin_user[1] # as of 17/6, admin has no entry in Student table, so they don't have email
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
            cursor.execute(query, (int(username),))
            user = cursor.fetchone()
            print(f"StudentID query result: {user}")
        else:
            print(f"Invalid username format: {username}")
            return None
        
        # Check regular user authentication
        if 'user' in locals() and user:
            stored_password = user[2]
            print(f"Stored password: '{stored_password}', Entered password: '{password}'")
            
            if password == stored_password:
                return {
                    'user_id': user[0],
                    'student_id': user[1],
                    'role': user[3],
                    'name': user[4],
                    'email': user[5]
                }
        
        print("Authentication failed - no matching user or wrong password")
        return None
        
    except Exception as e:
        print(f"Authentication error: {e}")
        return None
    finally:
        conn.close()

# Routes
@app.route('/')
def index():
    # Check if user is already logged in
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST']) # Login route
def login():
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Basic input validation
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')
        
        # Rate limiting would be implemented here in production
        
        # Authenticate user
        user = authenticate_user(username, password)
        
        if user:
            # Set session variables
            session.permanent = True
            session['user_id'] = user['user_id']
            session['student_id'] = user['student_id']
            session['role'] = user['role']
            session['name'] = user['name']
            session['email'] = user['email']
            session['login_time'] = datetime.now().isoformat()
            
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout') # Logout route
@login_required
def logout():
    name = session.get('name', 'User')
    session.clear()
    flash(f'Goodbye, {name}! You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard') # Dashboard route
@login_required
def dashboard():
    # Redirect admins to admin dashboard
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error. Please try again.', 'error')
        return redirect(url_for('logout'))
    
    try:
        cursor = conn.cursor()
        
        # Get user's CCAs
        cca_query = """
        SELECT c.CCAId, c.Name, c.Description, cm.CCARole
        FROM CCA c
        INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
        WHERE cm.UserId = ?
        """
        cursor.execute(cca_query, (session['user_id'],))
        user_ccas = cursor.fetchall()
        
        ccas = []
        user_is_moderator = False
        for cca in user_ccas:
            ccas.append({
                'id': cca[0],
                'name': cca[1],
                'description': cca[2],
                'role': cca[3]
            })
            # Check if user is moderator in any CCA
            if cca[3] == 'moderator':
                user_is_moderator = True
        
        # Get available polls for user's CCAs (ordered by most urgent first)
        # 17/6 - Changed to use v_Poll_With_LiveStatus view to auto close polls after end date - Dom
        if ccas:
            cca_ids = [str(cca['id']) for cca in ccas]
            poll_query = """
            SELECT p.PollId, p.Question, p.EndDate, c.Name as CCAName,
                DATEDIFF(day, GETDATE(), p.EndDate) as DaysRemaining
            FROM v_Poll_With_LiveStatus p
            INNER JOIN CCA c ON p.CCAId = c.CCAId
            WHERE p.CCAId IN ({}) AND p.LiveIsActive = 1
            ORDER BY p.EndDate ASC
            """.format(','.join(['?'] * len(cca_ids)))
            
            cursor.execute(poll_query, cca_ids)
            poll_results = cursor.fetchall()
            
            available_polls = []
            for poll in poll_results:
                available_polls.append({
                    'id': poll[0],
                    'title': poll[1],
                    'end_date': poll[2].strftime('%Y-%m-%d') if poll[2] else '',
                    'cca': poll[3],
                    'days_remaining': poll[4] if poll[4] is not None else 0
                })
        else:
            available_polls = []
        
        return render_template('dashboard.html', 
                             ccas=ccas, 
                             available_polls=available_polls,
                             user_name=session['name'],
                             user_role=session['role'],
                             user_is_moderator=user_is_moderator)
        
    except pyodbc.Error as e:
        print(f"Dashboard data error: {e}")
        flash('Error loading dashboard data.', 'error')
        return render_template('dashboard.html', 
                             ccas=[], 
                             available_polls=[],
                             user_name=session['name'],
                             user_role=session['role'],
                             user_is_moderator=False)
    finally:
        conn.close()

# Admin Dashboard
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error. Please try again.', 'error')
        return redirect(url_for('logout'))
    
    try:
        cursor = conn.cursor()
        
        # Get all CCAs
        cursor.execute("SELECT CCAId, Name, Description FROM CCA ORDER BY Name")
        all_ccas = cursor.fetchall()
        
        # Get all students
        cursor.execute("SELECT StudentId, Name, Email FROM Student ORDER BY Name")
        all_students = cursor.fetchall()
        
        # Get CCA memberships with details
        membership_query = """
        SELECT s.Name as StudentName, c.Name as CCAName, cm.CCARole, 
               s.StudentId, c.CCAId, cm.MemberId
        FROM CCAMembers cm
        INNER JOIN Student s ON cm.UserId IN (
            SELECT UserId FROM UserDetails WHERE StudentId = s.StudentId
        )
        INNER JOIN CCA c ON cm.CCAId = c.CCAId
        ORDER BY c.Name, s.Name
        """
        cursor.execute(membership_query)
        memberships = cursor.fetchall()
        
        return render_template('admin_dashboard.html',
                             ccas=all_ccas,
                             students=all_students,
                             memberships=memberships,
                             user_name=session['name'])
        
    except Exception as e:
        print(f"Admin dashboard error: {e}")
        flash('Error loading admin dashboard.', 'error')
        return render_template('admin_dashboard.html', 
                             ccas=[], students=[], memberships=[],
                             user_name=session['name'])
    finally:
        conn.close()

# Create Student Account 
@app.route('/admin/create-student', methods=['GET', 'POST'])
@admin_required
def create_student():
    if request.method == 'POST':
        # Get form data, student_id and password 
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '').strip()
        
        # Basic validation
        if not student_id or not password:
            flash('Both Student ID and password are required.', 'error')
            return render_template('create_student.html')
        
        if not validate_student_id(student_id):
            flash('Student ID must be 7 digits.', 'error')
            return render_template('create_student.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return render_template('create_student.html')
        
        try:
            cursor = conn.cursor()
            
            # Check if student exists in Student table
            cursor.execute("SELECT StudentId, Name FROM Student WHERE StudentId = ?", (int(student_id),))
            student_record = cursor.fetchone()
            
            if not student_record:
                flash(f'Student ID {student_id} not found in student records. Please contact administration to add student to system first.', 'error')
                return render_template('create_student.html')
            
            # Check if student already has a registered account
            cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
            existing_account = cursor.fetchone()
            
            if existing_account:
                flash(f'Student {student_record[1]} (ID: {student_id}) already has a login account.', 'error')
                return render_template('create_student.html')
            
            # Create an account if both checks pass
            cursor.execute("""
                INSERT INTO UserDetails (Username, StudentId, Password, SystemRole)
                VALUES (?, ?, ?, 'student')
            """, (int(student_id), int(student_id), password))
            
            conn.commit()
            flash(f'Login account created successfully for {student_record[1]} (ID: {student_id})!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            conn.rollback()
            print(f"Create student account error: {e}")
            flash('Error creating student account. Please try again.', 'error')
            return render_template('create_student.html')
        finally:
            conn.close()
    
    return render_template('create_student.html')

# Create CCA
@app.route('/admin/create-cca', methods=['GET', 'POST'])
@admin_required
def create_cca():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('CCA name is required.', 'error')
            return render_template('create_cca.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return render_template('create_cca.html')
        
        try:
            cursor = conn.cursor()
            
            # Check if CCA name already exists
            cursor.execute("SELECT CCAId FROM CCA WHERE Name = ?", (name,))
            if cursor.fetchone():
                flash('CCA name already exists.', 'error')
                return render_template('create_cca.html')
            
            # Insert new CCA
            cursor.execute("""
                INSERT INTO CCA (Name, Description)
                VALUES (?, ?)
            """, (name, description or ''))
            
            conn.commit()
            flash(f'CCA "{name}" created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            conn.rollback()
            print(f"Create CCA error: {e}")
            flash('Error creating CCA. Please try again.', 'error')
            return render_template('create_cca.html')
        finally:
            conn.close()
    
    return render_template('create_cca.html')

# View CCA Details
@app.route('/admin/cca/<int:cca_id>')
@admin_required
def view_cca(cca_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        cursor = conn.cursor()
        
        # Get CCA details
        cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
        cca = cursor.fetchone()
        
        if not cca:
            flash('CCA not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Get CCA members
        members_query = """
        SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId, ud.UserId
        FROM CCAMembers cm
        INNER JOIN UserDetails ud ON cm.UserId = ud.UserId
        INNER JOIN Student s ON ud.StudentId = s.StudentId
        WHERE cm.CCAId = ?
        ORDER BY s.Name
        """
        cursor.execute(members_query, (cca_id,))
        members = cursor.fetchall()
        
        # Get all students not in this CCA (for assignment)
        not_in_cca_query = """
        SELECT s.StudentId, s.Name
        FROM Student s
        INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
        WHERE ud.UserId NOT IN (
            SELECT UserId FROM CCAMembers WHERE CCAId = ?
        )
        ORDER BY s.Name
        """
        cursor.execute(not_in_cca_query, (cca_id,))
        available_students = cursor.fetchall()
        
        return render_template('view_cca.html', 
                             cca=cca, 
                             members=members, 
                             available_students=available_students)
        
    except Exception as e:
        print(f"View CCA error: {e}")
        flash('Error loading CCA details.', 'error')
        return redirect(url_for('admin_dashboard'))
    finally:
        conn.close()

# Edit CCA
@app.route('/admin/cca/<int:cca_id>/edit', methods=['POST'])
@admin_required
def edit_cca(cca_id):
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    if not name:
        flash('CCA name is required.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    
    try:
        cursor = conn.cursor()
        
        # Check if new name conflicts with existing CCAs (excluding current one)
        cursor.execute("SELECT CCAId FROM CCA WHERE Name = ? AND CCAId != ?", (name, cca_id))
        if cursor.fetchone():
            flash('CCA name already exists.', 'error')
            return redirect(url_for('view_cca', cca_id=cca_id))
        
        # Update CCA
        cursor.execute("""
            UPDATE CCA 
            SET Name = ?, Description = ?
            WHERE CCAId = ?
        """, (name, description, cca_id))
        
        conn.commit()
        flash('CCA updated successfully!', 'success')
        return redirect(url_for('view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Edit CCA error: {e}")
        flash('Error updating CCA.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Create Poll Route
@app.route('/create-poll', methods=['GET', 'POST'])
@moderator_required
def create_poll():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        cursor = conn.cursor()
        
        # Get CCAs where user is a moderator
        cursor.execute("""
            SELECT c.CCAId, c.Name, c.Description
            FROM CCA c
            INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
            WHERE cm.UserId = ? AND cm.CCARole = 'moderator'
            ORDER BY c.Name
        """, (session['user_id'],))
        moderator_ccas = cursor.fetchall()
        
        user_ccas = []
        for cca in moderator_ccas:
            user_ccas.append({
                'id': cca[0],
                'name': cca[1],
                'description': cca[2]
            })
        
        if request.method == 'POST':
            # Get form data
            cca_id = request.form.get('cca_id')
            question = request.form.get('question', '').strip()
            question_type = request.form.get('question_type')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            is_anonymous = request.form.get('is_anonymous') == '1'
            options = request.form.getlist('options[]')
            
            # Basic validation
            if not all([cca_id, question, question_type, start_date, end_date]):
                flash('Please fill in all required fields.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas, 
                                     user_name=session['name'], user_role='moderator')
            
            # Validate CCA access
            if not any(str(cca['id']) == str(cca_id) for cca in user_ccas):
                flash('You can only create polls for CCAs where you are a moderator.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
            
            # Filter and validate options
            valid_options = [opt.strip() for opt in options if opt.strip()]
            if len(valid_options) < 2:
                flash('Please provide at least 2 options for the poll.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
            
            if len(valid_options) > 10:
                flash('Maximum 10 options allowed.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
            
            # Check for duplicate options (case-insensitive)
            lower_options = [opt.lower() for opt in valid_options]
            if len(lower_options) != len(set(lower_options)):
                flash('Please ensure all options are unique.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
            
            # Validate dates
            try:
                start_datetime = datetime.fromisoformat(start_date)
                end_datetime = datetime.fromisoformat(end_date)
                
                if start_datetime >= end_datetime:
                    flash('End date must be after start date.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                         user_name=session['name'], user_role='moderator')
                
                if start_datetime < datetime.now():
                    flash('Start date cannot be in the past.', 'error')
                    return render_template('create_poll.html', user_ccas=user_ccas,
                                         user_name=session['name'], user_role='moderator')
                    
            except ValueError:
                flash('Invalid date format.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
            
            # Create poll in database
            try:
                # Insert poll
                cursor.execute("""
                    INSERT INTO Poll (CCAId, Question, QuestionType, StartDate, EndDate, IsAnonymous, IsActive)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (cca_id, question, question_type, start_datetime, end_datetime, is_anonymous))
                
                # Get the poll ID
                cursor.execute("SELECT @@IDENTITY")
                poll_id = cursor.fetchone()[0]
                
                # Insert options
                for option_text in valid_options:
                    cursor.execute("""
                        INSERT INTO Options (PollId, OptionText)
                        VALUES (?, ?)
                    """, (poll_id, option_text))
                
                conn.commit()
                
                # Get CCA name for success message
                cca_name = next(cca['name'] for cca in user_ccas if cca['id'] == int(cca_id))
                flash(f'Poll "{question}" created successfully for {cca_name}!', 'success')
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                conn.rollback()
                print(f"Create poll error: {e}")
                flash('Error creating poll. Please try again.', 'error')
                return render_template('create_poll.html', user_ccas=user_ccas,
                                     user_name=session['name'], user_role='moderator')
        
        return render_template('create_poll.html', user_ccas=user_ccas,
                             user_name=session['name'], user_role='moderator')
        
    except Exception as e:
        print(f"Create poll page error: {e}")
        flash('Error loading create poll page.', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# My CCAs route for moderators and students
@app.route('/my-ccas')
@login_required
def my_ccas():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        cursor = conn.cursor()
        
        # Get user's CCAs with their roles
        cca_query = """
        SELECT c.CCAId, c.Name, c.Description, cm.CCARole
        FROM CCA c
        INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
        WHERE cm.UserId = ?
        ORDER BY c.Name
        """
        cursor.execute(cca_query, (session['user_id'],))
        user_ccas = cursor.fetchall()
        
        ccas = []
        moderator_ccas = []
        for cca in user_ccas:
            cca_data = {
                'id': cca[0],
                'name': cca[1],
                'description': cca[2],
                'role': cca[3]
            }
            ccas.append(cca_data)
            if cca[3] == 'moderator':
                moderator_ccas.append(cca_data)
        
        return render_template('my_ccas.html', 
                             ccas=ccas, 
                             moderator_ccas=moderator_ccas,
                             user_name=session['name'],
                             user_role=session['role'])
        
    except Exception as e:
        print(f"My CCAs error: {e}")
        flash('Error loading CCAs.', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# Moderator CCA management
@app.route('/moderator/cca/<int:cca_id>')
@login_required
def moderator_view_cca(cca_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('my_ccas'))
    
    try:
        cursor = conn.cursor()
        
        # Check if user is moderator of this CCA
        cursor.execute("""
            SELECT COUNT(*) FROM CCAMembers 
            WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
        """, (session['user_id'], cca_id))
        is_moderator = cursor.fetchone()[0] > 0
        
        if not is_moderator:
            flash('Access denied. You are not a moderator of this CCA.', 'error')
            return redirect(url_for('my_ccas'))
        
        # Get CCA details
        cursor.execute("SELECT CCAId, Name, Description FROM CCA WHERE CCAId = ?", (cca_id,))
        cca = cursor.fetchone()
        
        if not cca:
            flash('CCA not found.', 'error')
            return redirect(url_for('my_ccas'))
        
        # Get CCA members
        members_query = """
        SELECT s.StudentId, s.Name, s.Email, cm.CCARole, cm.MemberId, ud.UserId
        FROM CCAMembers cm
        INNER JOIN UserDetails ud ON cm.UserId = ud.UserId
        INNER JOIN Student s ON ud.StudentId = s.StudentId
        WHERE cm.CCAId = ?
        ORDER BY s.Name
        """
        cursor.execute(members_query, (cca_id,))
        members = cursor.fetchall()
        
        # Get all students not in this CCA (for assignment)
        not_in_cca_query = """
        SELECT s.StudentId, s.Name
        FROM Student s
        INNER JOIN UserDetails ud ON s.StudentId = ud.StudentId
        WHERE ud.UserId NOT IN (
            SELECT UserId FROM CCAMembers WHERE CCAId = ?
        )
        ORDER BY s.Name
        """
        cursor.execute(not_in_cca_query, (cca_id,))
        available_students = cursor.fetchall()
        
        return render_template('moderator_view_cca.html', 
                             cca=cca, 
                             members=members, 
                             available_students=available_students,
                             user_name=session['name'])
        
    except Exception as e:
        print(f"Moderator view CCA error: {e}")
        flash('Error loading CCA details.', 'error')
        return redirect(url_for('my_ccas'))
    finally:
        conn.close()

# Edit CCA for moderators
@app.route('/moderator/cca/<int:cca_id>/edit', methods=['POST'])
@login_required
def moderator_edit_cca(cca_id):
    # Check if user is moderator of this CCA
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('my_ccas'))
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM CCAMembers 
            WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
        """, (session['user_id'], cca_id))
        is_moderator = cursor.fetchone()[0] > 0
        
        if not is_moderator:
            flash('Access denied. You are not a moderator of this CCA.', 'error')
            return redirect(url_for('my_ccas'))
        
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('CCA name is required.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        # Check if new name conflicts with existing CCAs (excluding current one)
        cursor.execute("SELECT CCAId FROM CCA WHERE Name = ? AND CCAId != ?", (name, cca_id))
        if cursor.fetchone():
            flash('CCA name already exists.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        # Update CCA
        cursor.execute("""
            UPDATE CCA 
            SET Name = ?, Description = ?
            WHERE CCAId = ?
        """, (name, description, cca_id))
        
        conn.commit()
        flash('CCA updated successfully!', 'success')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Moderator edit CCA error: {e}")
        flash('Error updating CCA.', 'error')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Add Student to CCA for moderators (Updated with role restriction)
@app.route('/moderator/cca/<int:cca_id>/add-student', methods=['POST'])
@login_required
def moderator_add_student_to_cca(cca_id):
    # Check if user is moderator of this CCA
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('my_ccas'))
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM CCAMembers 
            WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
        """, (session['user_id'], cca_id))
        is_moderator = cursor.fetchone()[0] > 0
        
        if not is_moderator:
            flash('Access denied. You are not a moderator of this CCA.', 'error')
            return redirect(url_for('my_ccas'))
        
        student_id = request.form.get('student_id')
        role = request.form.get('role')
        
        if not all([student_id, role]):
            flash('Please select both student and role.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        # IMPORTANT: Restrict moderators to only assign 'member' role
        if role != 'member':
            flash('Access denied. Moderators can only assign the "member" role to students. Contact an administrator to assign moderator roles.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        # Get UserId for the student
        cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
        user_result = cursor.fetchone()
        if not user_result:
            flash('Student not found.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        user_id = user_result[0]
        
        # Check if student is already a member of this CCA
        cursor.execute("SELECT COUNT(*) FROM CCAMembers WHERE UserId = ? AND CCAId = ?", (user_id, cca_id))
        if cursor.fetchone()[0] > 0:
            flash('Student is already a member of this CCA.', 'error')
            return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
        # Add to CCA with 'member' role only
        cursor.execute("""
            INSERT INTO CCAMembers (UserId, CCAId, CCARole)
            VALUES (?, ?, ?)
        """, (user_id, cca_id, 'member'))  # Force role to be 'member'
        
        conn.commit()
        
        # Get student name for success message
        cursor.execute("SELECT Name FROM Student WHERE StudentId = ?", (int(student_id),))
        student_name_result = cursor.fetchone()
        student_name = student_name_result[0] if student_name_result else f"Student {student_id}"
        
        flash(f'{student_name} has been added to the CCA as a member successfully!', 'success')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Moderator add student to CCA error: {e}")
        flash('Error adding student to CCA.', 'error')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Remove Student from CCA for moderators
@app.route('/moderator/cca/<int:cca_id>/remove-student/<int:member_id>', methods=['POST'])
@login_required
def moderator_remove_student_from_cca(cca_id, member_id):
    # Check if user is moderator of this CCA
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('my_ccas'))
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM CCAMembers 
            WHERE UserId = ? AND CCAId = ? AND CCARole = 'moderator'
        """, (session['user_id'], cca_id))
        is_moderator = cursor.fetchone()[0] > 0
        
        if not is_moderator:
            flash('Access denied. You are not a moderator of this CCA.', 'error')
            return redirect(url_for('my_ccas'))
        
        cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
        conn.commit()
        flash('Student removed from CCA successfully!', 'success')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Moderator remove student from CCA error: {e}")
        flash('Error removing student from CCA.', 'error')
        return redirect(url_for('moderator_view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Add Student to CCA
@app.route('/admin/cca/<int:cca_id>/add-student', methods=['POST'])
@admin_required
def add_student_to_cca(cca_id):
    student_id = request.form.get('student_id')
    role = request.form.get('role')
    
    if not all([student_id, role]):
        flash('Please select both student and role.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    
    try:
        cursor = conn.cursor()
        
        # Get UserId for the student
        cursor.execute("SELECT UserId FROM UserDetails WHERE StudentId = ?", (int(student_id),))
        user_result = cursor.fetchone()
        if not user_result:
            flash('Student not found.', 'error')
            return redirect(url_for('view_cca', cca_id=cca_id))
        
        user_id = user_result[0]
        
        # Add to CCA
        cursor.execute("""
            INSERT INTO CCAMembers (UserId, CCAId, CCARole)
            VALUES (?, ?, ?)
        """, (user_id, cca_id, role))
        
        conn.commit()
        flash('Student added to CCA successfully!', 'success')
        return redirect(url_for('view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Add student to CCA error: {e}")
        flash('Error adding student to CCA.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Remove Student from CCA
@app.route('/admin/cca/<int:cca_id>/remove-student/<int:member_id>', methods=['POST'])
@admin_required
def remove_student_from_cca(cca_id, member_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM CCAMembers WHERE MemberId = ? AND CCAId = ?", (member_id, cca_id))
        conn.commit()
        flash('Student removed from CCA successfully!', 'success')
        return redirect(url_for('view_cca', cca_id=cca_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Remove student from CCA error: {e}")
        flash('Error removing student from CCA.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    finally:
        conn.close()

# Delete CCA
@app.route('/admin/cca/<int:cca_id>/delete', methods=['POST'])
@admin_required
def delete_cca(cca_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        cursor = conn.cursor()
        
        # Get CCA name for confirmation message
        cursor.execute("SELECT Name FROM CCA WHERE CCAId = ?", (cca_id,))
        cca_result = cursor.fetchone()
        if not cca_result:
            flash('CCA not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        cca_name = cca_result[0]
        
        # Delete CCA members first (foreign key constraint)
        cursor.execute("DELETE FROM CCAMembers WHERE CCAId = ?", (cca_id,))
        
        # Delete any polls for this CCA
        cursor.execute("DELETE FROM Votes WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
        cursor.execute("DELETE FROM Options WHERE PollId IN (SELECT PollId FROM Poll WHERE CCAId = ?)", (cca_id,))
        cursor.execute("DELETE FROM Poll WHERE CCAId = ?", (cca_id,))
        
        # Delete the CCA
        cursor.execute("DELETE FROM CCA WHERE CCAId = ?", (cca_id,))
        
        conn.commit()
        flash(f'CCA "{cca_name}" and all related data deleted successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
        
    except Exception as e:
        conn.rollback()
        print(f"Delete CCA error: {e}")
        flash('Error deleting CCA.', 'error')
        return redirect(url_for('view_cca', cca_id=cca_id))
    finally:
        conn.close()

# View Polls
@app.route('/polls')
@login_required
def view_polls():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('dashboard'))

    try:
        cursor = conn.cursor()
        # Get CCAs the user is part of
        cursor.execute("""
            SELECT DISTINCT c.CCAId
            FROM CCA c
            INNER JOIN CCAMembers cm ON c.CCAId = cm.CCAId
            WHERE cm.UserId = ?
        """, (session['user_id'],))
        user_cca_ids_tuples = cursor.fetchall()
        user_cca_ids = [cca[0] for cca in user_cca_ids_tuples]

        polls_data = []
        if user_cca_ids:
            placeholders = ','.join(['?'] * len(user_cca_ids))
            # Use v_Poll_With_LiveStatus to get the calculated LiveIsActive
            sql_query = f"""
                SELECT p.PollId, p.CCAId, p.Question, p.QuestionType, p.StartDate, p.EndDate, p.IsAnonymous, p.LiveIsActive, cca.Name AS CCAName
                FROM v_Poll_With_LiveStatus p 
                JOIN CCA cca ON p.CCAId = cca.CCAId
                WHERE p.CCAId IN ({placeholders})
                ORDER BY p.EndDate DESC, p.StartDate DESC
            """
            cursor.execute(sql_query, user_cca_ids)
            polls_data = cursor.fetchall()

            processed_polls = []
            for row in polls_data:
                processed_polls.append({
                    'PollId': row[0], 
                    'CCAId': row[1], 
                    'Question': row[2], 
                    'QuestionType': row[3],
                    'StartDate': row[4].strftime('%Y-%m-%d %H:%M') if isinstance(row[4], datetime) else str(row[4]) if row[4] else 'N/A',
                    'EndDate': row[5].strftime('%Y-%m-%d %H:%M') if isinstance(row[5], datetime) else str(row[5]) if row[5] else 'N/A',
                    'IsAnonymous': row[6], 
                    'LiveIsActive': row[7], # This now comes from v_Poll_With_LiveStatus.LiveIsActive
                    'CCAName': row[8]
                })

        # If polls_data is empty, processed_polls will be empty.
        # Ensure processed_polls is defined even if there are no user_cca_ids or no polls.
        if not user_cca_ids or not polls_data:
            processed_polls = []

        return render_template('view_poll.html', polls=processed_polls, user_name=session.get('name'))

    except Exception as e:
        print(f"Error fetching polls: {e}")
        flash('Error fetching polls.', 'error')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            conn.close()

@app.route('/poll/<int:poll_id>')
@login_required
def view_poll_detail(poll_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('view_polls'))

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.PollId, p.Question, p.QuestionType, p.StartDate, p.EndDate, 
                   p.IsAnonymous, c.Name AS CCAName, p.LiveIsActive
            FROM v_Poll_With_LiveStatus p
            JOIN CCA c ON p.CCAId = c.CCAId
            WHERE p.PollId = ?
        """, (poll_id,))
        poll_data = cursor.fetchone()

        if not poll_data:
            flash('Poll not found.', 'error')
            return redirect(url_for('view_polls'))

        # Check if user is part of the CCA for this poll
        cursor.execute("""
            SELECT COUNT(*)
            FROM CCAMembers cm
            JOIN Poll p ON cm.CCAId = p.CCAId
            WHERE cm.UserId = ? AND p.PollId = ?
        """, (session['user_id'], poll_id))
        is_member_of_cca = cursor.fetchone()[0] > 0

        if not is_member_of_cca and session['role'] != 'admin': # Admins can view all polls
             flash('You do not have permission to view this poll.', 'error')
             return redirect(url_for('view_polls'))


        # Process poll data, including date formatting
        start_date_obj = poll_data[3]
        end_date_obj = poll_data[4]

        start_date_str = 'N/A'
        if isinstance(start_date_obj, datetime):
            start_date_str = start_date_obj.strftime('%Y-%m-%d %H:%M')
        elif start_date_obj: # Should ideally not be a string if DB type is datetime
            start_date_str = str(start_date_obj)

        end_date_str = 'N/A'
        if isinstance(end_date_obj, datetime):
            end_date_str = end_date_obj.strftime('%Y-%m-%d %H:%M')
        elif end_date_obj: # Should ideally not be a string
            end_date_str = str(end_date_obj)

        is_ended_status = False
        if isinstance(end_date_obj, datetime): # Use original datetime object for comparison
            is_ended_status = datetime.now() > end_date_obj
        
        poll = {
            'PollId': poll_data[0], 
            'Question': poll_data[1], 
            'QuestionType': poll_data[2],
            'StartDate': start_date_str,
            'EndDate': end_date_str, 
            'IsAnonymous': poll_data[5],
            'Description': None,  # No Description column in Poll table
            'CCAName': poll_data[6], 
            'LiveIsActive': poll_data[7], # Use LiveIsActive from the view
            'is_ended': is_ended_status
        }

        # Fetch poll options and vote counts
        cursor.execute("""
            SELECT o.OptionId, o.OptionText, COUNT(v.VoteId) AS VoteCount
            FROM Options o
            LEFT JOIN Votes v ON o.OptionId = v.OptionId
            WHERE o.PollId = ?
            GROUP BY o.OptionId, o.OptionText
            ORDER BY o.OptionId
        """, (poll_id,))
        options_data = cursor.fetchall()
        options = [{'OptionId': opt[0], 'OptionText': opt[1], 'VoteCount': opt[2]} for opt in options_data]

        # Check if user has already voted
        cursor.execute("""
            SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?
        """, (poll_id, session['user_id']))
        has_voted = cursor.fetchone()[0] > 0
        
        # Get user's previous votes if any (for multiple choice display)
        user_votes = []
        if has_voted and poll['QuestionType'] == 'multiple':
            cursor.execute("""
                SELECT OptionId FROM Votes WHERE PollId = ? AND UserId = ?
            """, (poll_id, session['user_id']))
            user_votes_data = cursor.fetchall()
            user_votes = [uv[0] for uv in user_votes_data]


        return render_template('poll_detail.html', poll=poll, options=options, has_voted=has_voted, user_votes=user_votes, user_name=session.get('name'))

    except Exception as e:
        print(f"Error fetching poll details for poll {poll_id}: {e}")
        flash('Error fetching poll details.', 'error')
        return redirect(url_for('view_polls'))
    finally:
        if conn:
            conn.close()

@app.route('/poll/<int:poll_id>/vote', methods=['POST'])
@login_required
def submit_vote(poll_id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('view_poll_detail', poll_id=poll_id))

    try:
        cursor = conn.cursor()

        # Fetch poll details to check if active, not ended, and user is eligible
        cursor.execute("SELECT LiveIsActive, CCAId, QuestionType FROM v_Poll_With_LiveStatus WHERE PollId = ?", (poll_id,))
        poll_info = cursor.fetchone()

        if not poll_info:
            flash('Poll not found.', 'error')
            return redirect(url_for('view_polls'))

        live_is_active, cca_id, question_type = poll_info

        if not live_is_active:
            flash('This poll is closed for voting.', 'error')
            return redirect(url_for('view_poll_detail', poll_id=poll_id))
        # Check if user is part of the CCA for this poll
        cursor.execute("""
            SELECT COUNT(*)
            FROM CCAMembers
            WHERE UserId = ? AND CCAId = ?
        """, (session['user_id'], cca_id))
        is_member_of_cca = cursor.fetchone()[0] > 0

        if not is_member_of_cca and session['role'] != 'admin': # Admins can bypass this check if needed for testing, but generally shouldn't vote
             flash('You are not a member of the CCA for this poll and cannot vote.', 'error')
             return redirect(url_for('view_poll_detail', poll_id=poll_id))

        # Check if user has already voted
        cursor.execute("SELECT COUNT(*) FROM Votes WHERE PollId = ? AND UserId = ?", (poll_id, session['user_id']))
        if cursor.fetchone()[0] > 0:
            flash('You have already voted in this poll.', 'info')
            return redirect(url_for('view_poll_detail', poll_id=poll_id))

        selected_option_ids = []
        if question_type == 'single':
            option_id = request.form.get('option')
            if not option_id:
                flash('Please select an option to vote.', 'error')
                return redirect(url_for('view_poll_detail', poll_id=poll_id))
            selected_option_ids.append(option_id)
        elif question_type == 'multiple':
            selected_option_ids = request.form.getlist('options') # Name of checkbox input in HTML
            if not selected_option_ids:
                flash('Please select at least one option to vote.', 'error')
                return redirect(url_for('view_poll_detail', poll_id=poll_id))
        else:
            flash('Invalid poll type.', 'error') # Should not happen
            return redirect(url_for('view_poll_detail', poll_id=poll_id))
        
        # Validate selected option IDs belong to the poll
        valid_option_ids_query = "SELECT OptionId FROM Options WHERE PollId = ?"
        cursor.execute(valid_option_ids_query, (poll_id,))
        valid_options_for_poll = [str(row[0]) for row in cursor.fetchall()]

        for opt_id in selected_option_ids:
            if opt_id not in valid_options_for_poll:
                flash(f'Invalid option selected: {opt_id}. Please try again.', 'error')
                return redirect(url_for('view_poll_detail', poll_id=poll_id))


        # Record the vote(s)
        for option_id in selected_option_ids:
            cursor.execute("""
                INSERT INTO Votes (PollId, OptionId, UserId, VoteDate)
                VALUES (?, ?, ?, GETDATE())
            """, (poll_id, int(option_id), session['user_id']))
        
        conn.commit()
        flash('Your vote has been recorded successfully!', 'success')

    except pyodbc.Error as db_err:
        conn.rollback()
        print(f"Database error during voting for poll {poll_id}: {db_err}")
        flash('A database error occurred while submitting your vote. Please try again.', 'error')
    except Exception as e:
        conn.rollback()
        print(f"Error submitting vote for poll {poll_id}: {e}")
        flash('An error occurred while submitting your vote. Please try again.', 'error')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('view_poll_detail', poll_id=poll_id))


if __name__ == '__main__':
    # Make sure to set debug=False in a production environment
    app.run(debug=True)
