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
        
        # Handle admin login specifically
        if username.lower() == 'admin':
            print("Admin login attempt...")
            query = """
            SELECT ud.UserId, ud.StudentId, ud.Password, ud.SystemRole
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
                    'name': 'Administrator',
                    'email': 'admin@ccap.sit'
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
        for cca in user_ccas:
            ccas.append({
                'id': cca[0],
                'name': cca[1],
                'description': cca[2],
                'role': cca[3]
            })
        
        # Get available polls for user's CCAs
        if ccas:
            cca_ids = [str(cca['id']) for cca in ccas]
            poll_query = """
            SELECT p.PollId, p.Question, p.EndDate, c.Name as CCAName
            FROM Poll p
            INNER JOIN CCA c ON p.CCAId = c.CCAId
            WHERE p.CCAId IN ({}) AND p.IsActive = 1 AND p.EndDate > GETDATE()
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
                    'cca': poll[3]
                })
        else:
            available_polls = []
        
        return render_template('dashboard.html', 
                             ccas=ccas, 
                             available_polls=available_polls,
                             user_name=session['name'],
                             user_role=session['role'])
        
    except pyodbc.Error as e:
        print(f"Dashboard data error: {e}")
        flash('Error loading dashboard data.', 'error')
        return render_template('dashboard.html', 
                             ccas=[], 
                             available_polls=[],
                             user_name=session['name'],
                             user_role=session['role'])
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
                INSERT INTO UserDetails (StudentId, Password, SystemRole)
                VALUES (?, ?, 'student')
            """, (int(student_id), password))
            
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

# Test database connection route (remove in production)
@app.route('/test-db')
def test_db():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Student")
            count = cursor.fetchone()[0]
            conn.close()
            return f"Database connection successful! Found {count} students."
        except Exception as e:
            return f"Database query error: {e}"
    else:
        return "Database connection failed!"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
