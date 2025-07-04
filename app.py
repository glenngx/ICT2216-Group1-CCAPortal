from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyodbc
from functools import wraps
import re
from datetime import datetime, timedelta
from email_service import email_service
import os  
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
# Removed direct import of DB_CONNECTION_STRING, SECRET_KEY from config
# try:
#     from config import DB_CONNECTION_STRING, SECRET_KEY
#     print("Configuration loaded from config.py")
# except ImportError:
#     print("ERROR: config.py file not found!")
#     exit(1)

# Import registration functions
from application.admin_routes import register_admin_routes
from application.moderator_routes import register_moderator_routes
from application.student_routes import register_student_routes
from application.misc_routes import register_misc_routes
from application.models import db

app = Flask(__name__)
# \*\ Added for Captcha
# 2️⃣  NEW  — make the key available in every template on every render
@app.context_processor
def inject_recaptcha_key():
    return dict(RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY"))
# \*\ Ended for Captcha

# Load configuration from config.py using from_object
try:
    app.config.from_object('config.Config')
    # \*\ For unit testing. Uncomment above ^ and add:
    
    #from config import Config
    #app.config.from_object(Config)
    
    # Access SECRET_KEY from app.config after loading
    app.secret_key = app.config['SECRET_KEY'] 
    print("Configuration loaded from config.Config object")
    email_service.init_app(app)  # Initialize email service
except ImportError:
    print("ERROR: Could not import config.Config. Make sure config.py and class Config exist.")
    exit(1)
except KeyError:
    print("ERROR: SECRET_KEY not found in config.Config.")
    exit(1)

# Manually set the SQLAlchemy Database URI from the config
app.config['SQLALCHEMY_DATABASE_URI'] = app.config.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = app.config.get('SQLALCHEMY_TRACK_MODIFICATIONS', False)

db.init_app(app)

# Session Management
app.config.update(
    # Commented out below, permanent set to False so cookies clear when browser closes
    # # Timeout after 30 min of inactivity
    # PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    # Prevent access to stored data from JavaScript
    SESSION_COOKIE_HTTPONLY=True,
    # Ensure cookies only sent over HTTPS
    SESSION_COOKIE_SECURE=True,
    # Protects against CSRF
    SESSION_COOKIE_SAMESITE='Strict'
)

# Database connection function
def get_db_connection():
    try:
        # Access DB_CONNECTION_STRING from app.config
        conn_str = app.config.get('DB_CONNECTION_STRING')
        if not conn_str:
            # Fallback to constructing it if DB_CONNECTION_STRING is not directly in Config
            # This assumes DB_DRIVER, DB_SERVER etc. are in config.Config
            driver = app.config['DB_DRIVER']
            server = app.config['DB_SERVER']
            name = app.config['DB_NAME']
            user = app.config['DB_USER']
            password = app.config['DB_PASSWORD']
            conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={name};UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
            app.config['DB_CONNECTION_STRING'] = conn_str # Store it for potential reuse

        conn = pyodbc.connect(conn_str)
        return conn
    except pyodbc.Error as e:
        print(f"Database connection error: {e}")
        return None
    except KeyError as e:
        print(f"Database configuration key error: {e} not found in app.config. Make sure DB_DRIVER, DB_SERVER, etc. are set in config.Config.")
        return None

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('misc_routes.login')) # Updated url_for
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('misc_routes.login')) # Updated url_for
        
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('misc_routes.login')) # Updated url_for
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('misc_routes.login')) # Updated url_for
        
        # Check session for admin role
        if session.get('role') != 'admin':
            flash('Access denied.', 'error')
            return redirect(url_for('student_routes.dashboard')) # Updated url_for
        
        # Check db for user role
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard')) # Updated url_for
        
        try:
            print(session['user_id'])
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM UserDetails 
                WHERE UserId = ? AND SystemRole = 'admin'
            """, (session['user_id'],))
            is_admin = cursor.fetchone()[0] > 0
            
            if not is_admin:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.dashboard')) # Updated url_for
        
        except Exception as e:
            print(f"Admin check error: {e}")
            flash('Error checking permissions.', 'error')
            return redirect(url_for('student_routes.dashboard')) # Updated url_for
        finally:
            conn.close()
        
        return f(*args, **kwargs)
    return decorated_function

# Moderator required decorator
def moderator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('misc_routes.login')) # Updated url_for
        
        # Check if session is expired
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('misc_routes.login')) # Updated url_for
        
        # Check if user is a moderator in any CCA
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('student_routes.dashboard')) # Updated url_for
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM CCAMembers 
                WHERE UserId = ? AND CCARole = 'moderator'
            """, (session['user_id'],))
            is_moderator = cursor.fetchone()[0] > 0
            
            if not is_moderator:
                flash('Access denied.', 'error')
                return redirect(url_for('student_routes.dashboard')) # Updated url_for
            
        except Exception as e:
            print(f"Moderator check error: {e}")
            flash('Error checking permissions.', 'error')
            return redirect(url_for('student_routes.dashboard')) # Updated url_for
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

# Register routes from separate files
register_misc_routes(app, get_db_connection, login_required, validate_email, validate_student_id)
register_student_routes(app, get_db_connection, login_required)
register_moderator_routes(app, get_db_connection)
register_admin_routes(app, get_db_connection, validate_student_id)

@app.route('/health')
def health_check():
    """Health check endpoint for Docker"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}, 200
        else:
            return {'status': 'unhealthy', 'database': 'disconnected'}, 503
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 503
    

# Global Error Handlers 
# Global 404 error handler (non-existing path)
@app.errorhandler(404)
def page_not_found(error):
    path = request.path.lower()

    # Suppress flash/redirect for static resources and icons
    if (
        path.startswith('/static/')
        or path.startswith('/.well-known/') # Chrome-side Devtools
        or path.endswith('.ico')
        or path.endswith('.png')
        or path.endswith('.jpg')
        or path.endswith('.jpeg')
        or path.endswith('.svg')
        or path.endswith('.js')
        or path.endswith('.css')
        or path.endswith('.woff')
        or path.endswith('.ttf')
        or path.endswith('.map')
    ):
        print(f"[DEBUG] Ignored 404 (asset): {path}")
        return '', 204  # No content response

    # Only for unknown route 404s:
    print(f"[DEBUG] Flashing 404 warning for: {path}")
    flash("Access Denied 404.", "error")
    return redirect(url_for('student_routes.dashboard')), 302


# Global 500 error handler (internal server error)
@app.errorhandler(500)
def handle_500(error):
    flash("An unexpected error occurred.", "error")
    return redirect(url_for('student_routes.dashboard')), 302


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
