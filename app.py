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

@app.route('/login', methods=['GET', 'POST'])
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

@app.route('/logout')
@login_required
def logout():
    name = session.get('name', 'User')
    session.clear()
    flash(f'Goodbye, {name}! You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's CCAs and available polls from database
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
