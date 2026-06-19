import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = False
    TESTING = False
    
    # Database - Using XAMPP MySQL with mysql.connector (already installed)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL', 
        'mysql+mysqlconnector://root@localhost:3306/agrisearch'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Session - Extended timeout for better UX
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)  # Sessions last 7 days
    SESSION_REFRESH_EACH_REQUEST = True  # Refresh timeout on each request
    SESSION_COOKIE_SECURE = False  # True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent JS access
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    
    # Victoria Configuration
    VICTORIA_ENABLED = os.getenv('VICTORIA_SYSTEM_ENABLED', 'true').lower() == 'true'
    VICTORIA_BOUNDS = {
        'min_lat': float(os.getenv('VICTORIA_MIN_LATITUDE', 14.17)),
        'max_lat': float(os.getenv('VICTORIA_MAX_LATITUDE', 14.28)),
        'min_lng': float(os.getenv('VICTORIA_MIN_LONGITUDE', 121.30)),
        'max_lng': float(os.getenv('VICTORIA_MAX_LONGITUDE', 121.35))
    }
    
    # Email Configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME', 'noreply@agrisearch.local')

    # Public landing chatbot demo limits
    CHATBOT_DEMO_ENABLED = os.getenv('CHATBOT_DEMO_ENABLED', 'true').lower() == 'true'
    CHATBOT_DEMO_MAX_MESSAGE_CHARS = int(os.getenv('CHATBOT_DEMO_MAX_MESSAGE_CHARS', 600))
    CHATBOT_DEMO_MAX_HISTORY_ITEMS = int(os.getenv('CHATBOT_DEMO_MAX_HISTORY_ITEMS', 8))
    CHATBOT_DEMO_MAX_MESSAGES_PER_WINDOW = int(os.getenv('CHATBOT_DEMO_MAX_MESSAGES_PER_WINDOW', 8))
    CHATBOT_DEMO_WINDOW_SECONDS = int(os.getenv('CHATBOT_DEMO_WINDOW_SECONDS', 900))
    
    # Roles
    ALLOWED_ROLES = [
        'system_admin',
        'victoria_admin',
        'farmer'
    ]
    
    # Victoria Barangays
    VICTORIA_BARANGAYS = {
        1: {'code': 'VIC-001', 'name': 'Banca-Banca'},
        2: {'code': 'VIC-002', 'name': 'Daniw'},
        3: {'code': 'VIC-003', 'name': 'Masapang'},
        4: {'code': 'VIC-004', 'name': 'Nanhaya'},
        5: {'code': 'VIC-005', 'name': 'Pagalangan'},
        6: {'code': 'VIC-006', 'name': 'San Benito'},
        7: {'code': 'VIC-007', 'name': 'San Felix'},
        8: {'code': 'VIC-008', 'name': 'San Francisco'},
        9: {'code': 'VIC-009', 'name': 'San Roque'}
    }


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
