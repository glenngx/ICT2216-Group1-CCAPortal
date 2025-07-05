# Database Configuration
# DO NOT COMMIT THIS FILE TO GIT, should already be in .gitignore
import secrets
import os

class Config:
    # Database Configuration
    DB_DRIVER = "ODBC Driver 18 for SQL Server"
    DB_SERVER = "tcp:ict2116.database.windows.net,1433"
    DB_NAME = "ict2216"
    DB_USER = "ict2116"
    DB_PASSWORD = "RedBull]2"
    DB_CONNECTION_STRING = f"DRIVER={{{DB_DRIVER}}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD};Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"
    
    # Flask Configuration
    SECRET_KEY = "Ty0t7P@q5z))$EwB,!~_`ND$nr$P#4Vs7jhL/cat}VaH"
    
    # Email Configuration (Flask-Mail)
    # For Gmail SMTP (recommended for development/testing)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')  
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    # Application specific settings
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@sit.edu.sg')
    SITE_NAME = 'CCA Portal'
    SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5000')  # Update this later for production
    
    # Token expiration, 24 hours
    PASSWORD_RESET_TOKEN_EXPIRE = 24 * 60 * 60
    
    # Other Flask settings
    DEBUG = True

    # SQLAlchemy Configuration
    SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc://{DB_USER}:{DB_PASSWORD}@{DB_SERVER.replace('tcp:', '')}/{DB_NAME}?driver={DB_DRIVER.replace(' ', '+')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False