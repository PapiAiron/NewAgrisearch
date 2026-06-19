"""
Database initialization and setup
"""
import mysql.connector
from mysql.connector import Error
import os

def get_db_config():
    """Get database configuration from environment variables"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'agrisearch')
    }

def create_database_if_not_exists():
    """
    Create the database if it doesn't exist
    This connects to MySQL without specifying a database first
    """
    config = get_db_config()
    db_name = config.pop('database')  # Remove database name from config
    
    try:
        print(f"[DB] Checking if database '{db_name}' exists...")
        
        # Connect to MySQL server without database
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        
        # Check if database exists using parameterized query
        cursor.execute("SHOW DATABASES LIKE %s", (db_name,))
        result = cursor.fetchone()
        
        if result:
            print(f"[OK] Database '{db_name}' already exists")
        else:
            # Create database if it doesn't exist (backtick-quoted for safety)
            print(f"[DB] Creating database '{db_name}'...")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            connection.commit()
            print(f"[OK] Database '{db_name}' created successfully")
        
        cursor.close()
        connection.close()
        
        return True
        
    except Error as e:
        print(f"[ERROR] Error checking/creating database: {e}")
        return False

if __name__ == '__main__':
    create_database_if_not_exists()
