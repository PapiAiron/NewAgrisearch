from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
from enum import Enum

class UserRole(Enum):
    """User role enumeration"""
    SYSTEM_ADMIN = 'system_admin'
    VICTORIA_ADMIN = 'victoria_admin'
    FARMER = 'farmer'


class User(db.Model):
    """User model"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    
    # Role and Location
    role = db.Column(db.String(30), nullable=False, default='farmer')
    barangay_id = db.Column(db.Integer)
    barangay_name = db.Column(db.String(100))
    
    # Account Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_verified = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    password_resets = db.relationship('PasswordReset', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'barangay_id': self.barangay_id,
            'barangay_name': self.barangay_name,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class PasswordReset(db.Model):
    """Password reset token model"""
    __tablename__ = 'password_resets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<PasswordReset {self.user_id}>'
    
    @staticmethod
    def generate_token():
        """Generate a unique reset token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def create_reset_token(user_id, expires_in_hours=24):
        """Create a new password reset token"""
        token = PasswordReset.generate_token()
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        
        reset = PasswordReset(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        
        db.session.add(reset)
        db.session.commit()
        
        return token
    
    @staticmethod
    def verify_token(token):
        """Verify a reset token and return the user if valid"""
        reset = PasswordReset.query.filter_by(
            token=token,
            is_used=False
        ).first()
        
        if not reset or reset.expires_at < datetime.utcnow():
            return None
        
        return reset.user
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        db.session.commit()
