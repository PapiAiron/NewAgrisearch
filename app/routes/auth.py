from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from app import db
from app.models.user import User, PasswordReset
from functools import wraps
from datetime import datetime
import logging
import re
from config import Config

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember')
        
        logger.info(f"[LOGIN] Attempt with username: {username}")
        
        # Validate input
        if not username or not password:
            logger.warning(f"[LOGIN] Missing credentials for: {username}")
            flash('Username and password are required.', 'error')
            return redirect(url_for('auth.login'))
        
        # Find user
        try:
            user = User.query.filter(
                (User.username == username) | (User.email == username)
            ).first()
            logger.info(f"[LOGIN] User lookup result: {user.username if user else 'NOT FOUND'}")
        except Exception as e:
            logger.error(f"[LOGIN] Database error during user lookup: {str(e)}")
            flash('Login system error. Please try again.', 'error')
            return redirect(url_for('auth.login'))
        
        if not user or not user.check_password(password):
            logger.warning(f"[LOGIN] Invalid credentials for: {username}")
            flash('Invalid username or password.', 'error')
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            logger.warning(f"[LOGIN] Inactive account: {username}")
            flash('Your account has been deactivated. Contact administrator.', 'error')
            return redirect(url_for('auth.login'))
        
        # Update last login
        try:
            user.last_login = datetime.utcnow()
            db.session.commit()
            logger.info(f"[LOGIN] Updated last_login for user: {username}")
        except Exception as e:
            logger.error(f"[LOGIN] Error updating last_login: {str(e)}")
            db.session.rollback()
        
        # Set session - ALWAYS permanent for consistent timeout handling
        try:
            session.permanent = True if remember else False
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['full_name'] = user.full_name
            logger.info(f"[LOGIN] Session data set for user_id: {user.id}, session keys: {list(session.keys())}")
        except Exception as e:
            logger.error(f"[LOGIN] Error setting session: {str(e)}")
            flash('Session error. Please try again.', 'error')
            return redirect(url_for('auth.login'))
        
        logger.info(f"[LOGIN] SUCCESS for user: {username} (id: {user.id})")
        flash(f'Welcome back, {user.full_name}!', 'success')
        
        # Check session before redirect
        logger.info(f"[LOGIN] Session before redirect: user_id={session.get('user_id')}, permanent={session.permanent}")
        
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page and handler"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        full_name = request.form.get('full_name', '').strip()
        barangay_id = request.form.get('barangay_id')
        
        # Validate input
        if not all([username, email, password, password_confirm, full_name, barangay_id]):
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Invalid email format.', 'error')
            return redirect(url_for('auth.register'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.register'))
        
        if password != password_confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register'))
        
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'error')
            return redirect(url_for('auth.register'))
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('auth.register'))
        
        # Validate barangay
        try:
            barangay_id_int = int(barangay_id)
            if barangay_id_int not in Config.VICTORIA_BARANGAYS:
                flash('Invalid barangay selected.', 'error')
                return redirect(url_for('auth.register'))
        except (ValueError, TypeError):
            flash('Invalid barangay selection.', 'error')
            return redirect(url_for('auth.register'))
        
        # Create user
        try:
            barangay = Config.VICTORIA_BARANGAYS[barangay_id_int]
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                role='farmer',  # Default role for new users
                barangay_id=barangay_id_int,
                barangay_name=barangay['name'],
                is_active=True,
                is_verified=False  # Can be verified via email later
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"[REGISTER] New user created: {username}")
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[REGISTER] Error creating user: {str(e)}", exc_info=True)
            flash(f'Registration error: {str(e)}', 'error')
            return redirect(url_for('auth.register'))
    
    # Get barangays for dropdown
    barangays = Config.VICTORIA_BARANGAYS
    
    return render_template('auth/register.html', barangays=barangays)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page and handler"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        user = User.query.filter_by(email=email).first()
        
        # For security, we don't reveal if email exists
        if user:
            token = PasswordReset.create_reset_token(user.id)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # In production, send email here
            # send_reset_email(user.email, reset_url)
            
            # For development, we'll show the link
            flash(f'Password reset link has been generated. Reset URL: {reset_url}', 'info')
        else:
            flash('If email exists, password reset link will be sent.', 'info')
        
        return redirect(url_for('auth.forgot_password'))
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page and handler"""
    reset_record = PasswordReset.query.filter_by(token=token, is_used=False).first()
    
    if not reset_record or reset_record.expires_at < datetime.utcnow():
        logger.warning(f"[RESET_PASSWORD] Invalid or expired token: {token}")
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    user = reset_record.user
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        if not password or not password_confirm:
            flash('Password is required.', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        if password != password_confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        # Update password
        try:
            user.set_password(password)
            reset_record.mark_as_used()
            db.session.commit()
            
            logger.info(f"[RESET_PASSWORD] Password reset for user: {user.username}")
            flash('Password has been reset successfully. You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[RESET_PASSWORD] Error resetting password: {str(e)}", exc_info=True)
            flash('Error resetting password. Please try again.', 'error')
            return redirect(url_for('auth.reset_password', token=token))
    
    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
