#!/usr/bin/env python
"""
Script to seed sample users for each role
"""
import os
from app import create_app, db
from app.models.user import User
from datetime import datetime

app = create_app(os.getenv('FLASK_ENV', 'development'))

# Sample users for each role
sample_users = [
    {
        'username': 'admin_system',
        'email': 'admin@agrisearch.local',
        'password': 'Admin@123456',
        'full_name': 'System Administrator',
        'role': 'system_admin',
        'barangay_id': 1,
        'barangay_name': 'Banca-Banca'
    },
    {
        'username': 'admin_victoria',
        'email': 'victoria_admin@agrisearch.local',
        'password': 'Admin@123456',
        'full_name': 'Victoria Administrator',
        'role': 'victoria_admin',
        'barangay_id': 1,
        'barangay_name': 'Banca-Banca'
    },
    {
        'username': 'farmer_juan',
        'email': 'farmer@agrisearch.local',
        'password': 'Farmer@123456',
        'full_name': 'Juan dela Cruz',
        'role': 'farmer',
        'barangay_id': 4,
        'barangay_name': 'Nanhaya'
    }
]

def seed_database():
    """Create sample users in the database"""
    with app.app_context():
        print("🌾 Seeding AgriSearch database with sample users...")
        
        # Check if users already exist
        existing_users = User.query.count()
        if existing_users > 0:
            print(f"⚠️  Database already has {existing_users} user(s). Skipping seed.")
            return
        
        try:
            for user_data in sample_users:
                # Create user
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    full_name=user_data['full_name'],
                    role=user_data['role'],
                    barangay_id=user_data['barangay_id'],
                    barangay_name=user_data['barangay_name'],
                    is_active=True,
                    is_verified=True
                )
                
                # Set password
                user.set_password(user_data['password'])
                
                # Add to session
                db.session.add(user)
                
                print(f"✅ Created user: {user_data['username']} ({user_data['role']})")
            
            # Commit all changes
            db.session.commit()
            
            print("\n" + "="*60)
            print("🎉 Sample users created successfully!")
            print("="*60)
            print("\nSample User Credentials:")
            print("-" * 60)
            
            for user_data in sample_users:
                print(f"\nRole: {user_data['role'].upper()}")
                print(f"  Username: {user_data['username']}")
                print(f"  Email: {user_data['email']}")
                print(f"  Password: {user_data['password']}")
                print(f"  Barangay: {user_data['barangay_name']}")
            
            print("\n" + "="*60)
            print("Login at: http://127.0.0.1:5000/auth/login")
            print("="*60)
            
        except Exception as e:
            print(f"❌ Error seeding database: {e}")
            db.session.rollback()

if __name__ == '__main__':
    seed_database()
