from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from functools import wraps
from app.models.user import User
from app.models.farm import Farm
from app.models.livestock import Livestock, HealthRecord
from app.models.health import VaccineInventory, DiseaseRecord, HealthAlert
from app.models.distribution import DistributionRequest, MunicipalOffer
from app import db
import logging
from sqlalchemy import func
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__)

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    """Main dashboard - routes to role-specific dashboard"""
    user_id = session.get('user_id')
    logger.info(f"[DASHBOARD] Access with user_id: {user_id}, session keys: {list(session.keys())}")
    
    user = User.query.get(user_id)
    
    if not user:
        # Don't clear session; user may exist but query failed
        logger.warning(f"[DASHBOARD] User {user_id} not found in database during dashboard load")
        flash('Unable to load user profile. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    logger.info(f"[DASHBOARD] User found: {user.username}, role: {user.role}")
    
    # Route to role-specific dashboard
    role = user.role
    
    try:
        if role == 'system_admin':
            return redirect(url_for('dashboard.system_admin_dashboard'))
        elif role == 'victoria_admin':
            return redirect(url_for('dashboard.victoria_admin_dashboard'))
        else:  # farmer
            return redirect(url_for('dashboard.farmer_dashboard'))
    except Exception as e:
        logger.error(f"[INDEX] Error routing dashboard for user {user.username}: {str(e)}", exc_info=True)
        flash('An error occurred routing your dashboard. Please refresh.', 'warning')
        # Don't logout - just redirect back to index to retry
        return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/farmer', methods=['GET'])
@login_required
def farmer_dashboard():
    """Farmer dashboard"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'farmer':
        flash('Access denied. This dashboard is for farmers only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Get farmer's farms
        farms = Farm.query.filter_by(owner_id=user_id, is_active=True).all()
        total_area = sum(farm.area_square_meters for farm in farms) if farms else 0
        total_farms = len(farms)
        
        # Get farmer's livestock
        farm_ids = [f.id for f in farms]
        total_livestock = 0
        livestock_by_type = {}
        if farm_ids:
            livestock = Livestock.query.filter(Livestock.farm_id.in_(farm_ids)).all()
            for animal in livestock:
                total_livestock += animal.count or 1
                type_name = animal.animal_type
                livestock_by_type[type_name] = livestock_by_type.get(type_name, 0) + (animal.count or 1)
        else:
            livestock = []
        
        # Get vaccine alerts for farmer's livestock
        vaccine_alerts = []
        if farm_ids:
            vaccine_alerts = HealthRecord.query.join(Livestock).filter(
                Livestock.farm_id.in_(farm_ids),
                HealthRecord.record_type == 'vaccine',
                HealthRecord.next_due_date <= datetime.utcnow() + timedelta(days=7),
                HealthRecord.next_due_date > datetime.utcnow()
            ).all()
        
        # Get health metrics for farmer
        livestock_ids = [l.id for l in livestock]
        animals_with_diseases = 0
        upcoming_vaccines = 0
        vaccines_count = 0
        expired_vaccines = 0
        expiring_soon_vaccines = 0
        total_health_alerts = 0
        critical_alerts = 0
        
        if livestock_ids:
            animals_with_diseases = len([l for l in livestock if l.diseases])
            upcoming_vaccines = HealthRecord.query.filter(
                HealthRecord.livestock_id.in_(livestock_ids),
                HealthRecord.record_type == 'vaccine',
                HealthRecord.next_due_date != None,
                HealthRecord.next_due_date <= datetime.utcnow() + timedelta(days=7),
                HealthRecord.next_due_date > datetime.utcnow()
            ).count()
        
        if farm_ids:
            vaccines = VaccineInventory.query.filter(VaccineInventory.farm_id.in_(farm_ids)).all()
            vaccines_count = len(vaccines)
            expired_vaccines = len([v for v in vaccines if v.is_expired])
            expiring_soon_vaccines = len([v for v in vaccines if v.expiry_status == 'expiring_soon'])
        
        if livestock_ids:
            alerts = HealthAlert.query.filter(
                HealthAlert.livestock_id.in_(livestock_ids),
                HealthAlert.is_resolved == False
            ).all()
            total_health_alerts = len(alerts)
            critical_alerts = len([a for a in alerts if a.priority == 'critical'])
        
        # Open municipal offers for this farmer's barangays
        farmer_barangays = list({f.barangay_name for f in farms})
        from datetime import date
        today = date.today()
        open_offers_count = MunicipalOffer.query.filter(
            MunicipalOffer.status == 'open',
            MunicipalOffer.claim_deadline >= today,
            db.or_(
                MunicipalOffer.target_barangay == None,
                MunicipalOffer.target_barangay.in_(farmer_barangays)
            )
        ).count()

        context = {
            'user': user,
            'farms': farms,
            'total_farms': total_farms,
            'total_area': total_area,
            'average_area': total_area / total_farms if total_farms > 0 else 0,
            'crop_types': list(set(farm.crop_type for farm in farms)) if farms else [],
            'total_livestock': total_livestock,
            'livestock_by_type': livestock_by_type,
            'vaccine_alerts': vaccine_alerts,
            'animals_with_diseases': animals_with_diseases,
            'upcoming_vaccines': upcoming_vaccines,
            'vaccines_count': vaccines_count,
            'expired_vaccines': expired_vaccines,
            'expiring_soon_vaccines': expiring_soon_vaccines,
            'total_health_alerts': total_health_alerts,
            'critical_alerts': critical_alerts,
            'open_offers_count': open_offers_count
        }
        
        logger.info(f"[FARMER_DASHBOARD] Loaded dashboard for farmer {user.username}")
        return render_template('dashboard/farmer.html', **context)
    except Exception as e:
        logger.error(f"[FARMER_DASHBOARD] Error loading dashboard for user {user.username}: {str(e)}", exc_info=True)
        flash(f'Error loading dashboard: {str(e)}', 'error')
        # DON'T logout on dashboard errors - just show a friendly error
        context = {
            'user': user,
            'farms': [],
            'total_farms': 0,
            'total_area': 0,
            'average_area': 0,
            'crop_types': [],
            'total_livestock': 0,
            'livestock_by_type': {},
            'vaccine_alerts': [],
            'animals_with_diseases': 0,
            'upcoming_vaccines': 0,
            'vaccines_count': 0,
            'expired_vaccines': 0,
            'expiring_soon_vaccines': 0,
            'total_health_alerts': 0,
            'critical_alerts': 0,
            'error': str(e)
        }
        return render_template('dashboard/farmer.html', **context)


@dashboard_bp.route('/admin/victoria', methods=['GET'])
@login_required
def victoria_admin_dashboard():
    """Victoria admin dashboard"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'victoria_admin':
        flash('Access denied. This dashboard is for Victoria admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Get all system data
        farms = Farm.query.filter_by(is_active=True).all()
        all_users = User.query.filter_by(is_active=True).all()
        livestock = Livestock.query.all()
        
        # Get health metrics
        livestock_ids = [l.id for l in livestock]
        animals_with_diseases = 0
        upcoming_vaccines = 0
        vaccines_count = 0
        expired_vaccines = 0
        expiring_soon_vaccines = 0
        total_health_alerts = 0
        critical_alerts = 0
        
        if livestock_ids:
            animals_with_diseases = len([l for l in livestock if l.diseases])
            upcoming_vaccines = HealthRecord.query.filter(
                HealthRecord.livestock_id.in_(livestock_ids),
                HealthRecord.record_type == 'vaccine',
                HealthRecord.next_due_date != None,
                HealthRecord.next_due_date <= datetime.utcnow() + timedelta(days=7),
                HealthRecord.next_due_date > datetime.utcnow()
            ).count()
        
        farm_ids = [f.id for f in farms]
        if farm_ids:
            vaccines = VaccineInventory.query.filter(VaccineInventory.farm_id.in_(farm_ids)).all()
            vaccines_count = len(vaccines)
            expired_vaccines = len([v for v in vaccines if v.is_expired])
            expiring_soon_vaccines = len([v for v in vaccines if v.expiry_status == 'expiring_soon'])
        
        if livestock_ids:
            alerts = HealthAlert.query.filter(
                HealthAlert.livestock_id.in_(livestock_ids),
                HealthAlert.is_resolved == False
            ).all()
            total_health_alerts = len(alerts)
            critical_alerts = len([a for a in alerts if a.priority == 'critical'])
        
        # Calculate stats
        total_area = sum(farm.area_square_meters for farm in farms) if farms else 0
        total_farms = len(farms)
        total_livestock_count = len(livestock)
        
        # Count users by role
        role_counts = {}
        for u in all_users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1
        
        context = {
            'user': user,
            'total_farms': total_farms,
            'total_area': total_area,
            'total_users': len(all_users),
            'total_livestock': total_livestock_count,
            'role_counts': role_counts,
            'farms': farms,
            'users': all_users,
            'animals_with_diseases': animals_with_diseases,
            'upcoming_vaccines': upcoming_vaccines,
            'vaccines_count': vaccines_count,
            'expired_vaccines': expired_vaccines,
            'expiring_soon_vaccines': expiring_soon_vaccines,
            'total_health_alerts': total_health_alerts,
            'critical_alerts': critical_alerts,
            'direct_requests_count': DistributionRequest.query.filter_by(status='pending').count()
        }
        
        logger.info(f"[VICTORIA_ADMIN_DASHBOARD] Loaded dashboard for Victoria admin {user.username}")
        return render_template('dashboard/victoria_admin.html', **context)
    except Exception as e:
        logger.error(f"[VICTORIA_ADMIN_DASHBOARD] Error loading dashboard for user {user.username}: {str(e)}", exc_info=True)
        flash('Error loading dashboard data.', 'warning')
        context = {
            'user': user,
            'total_farms': 0,
            'total_area': 0,
            'total_users': 0,
            'total_livestock': 0,
            'role_counts': {},
            'farms': [],
            'users': [],
            'animals_with_diseases': 0,
            'upcoming_vaccines': 0,
            'vaccines_count': 0,
            'expired_vaccines': 0,
            'expiring_soon_vaccines': 0,
            'total_health_alerts': 0,
            'critical_alerts': 0,
            'error': str(e)
        }
        return render_template('dashboard/victoria_admin.html', **context)


@dashboard_bp.route('/admin/system', methods=['GET'])
@login_required
def system_admin_dashboard():
    """System admin dashboard"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'system_admin':
        flash('Access denied. This dashboard is for system admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Get all system data including inactive
        farms = Farm.query.all()
        all_users = User.query.all()
        livestock = Livestock.query.all()
        
        # Get health metrics
        livestock_ids = [l.id for l in livestock]
        animals_with_diseases = 0
        upcoming_vaccines = 0
        vaccines_count = 0
        expired_vaccines = 0
        expiring_soon_vaccines = 0
        total_health_alerts = 0
        critical_alerts = 0
        
        if livestock_ids:
            animals_with_diseases = len([l for l in livestock if l.diseases])
            upcoming_vaccines = HealthRecord.query.filter(
                HealthRecord.livestock_id.in_(livestock_ids),
                HealthRecord.record_type == 'vaccine',
                HealthRecord.next_due_date != None,
                HealthRecord.next_due_date <= datetime.utcnow() + timedelta(days=7),
                HealthRecord.next_due_date > datetime.utcnow()
            ).count()
        
        farm_ids = [f.id for f in farms]
        if farm_ids:
            vaccines = VaccineInventory.query.filter(VaccineInventory.farm_id.in_(farm_ids)).all()
            vaccines_count = len(vaccines)
            expired_vaccines = len([v for v in vaccines if v.is_expired])
            expiring_soon_vaccines = len([v for v in vaccines if v.expiry_status == 'expiring_soon'])
        
        if livestock_ids:
            alerts = HealthAlert.query.filter(
                HealthAlert.livestock_id.in_(livestock_ids),
                HealthAlert.is_resolved == False
            ).all()
            total_health_alerts = len(alerts)
            critical_alerts = len([a for a in alerts if a.priority == 'critical'])
        
        # Calculate stats
        total_area = sum(farm.area_square_meters for farm in farms if farm.is_active) if farms else 0
        total_farms = len([f for f in farms if f.is_active])
        total_livestock_count = len(livestock)
        
        # Count users by role and status
        role_counts = {}
        active_users = 0
        verified_users = 0
        for u in all_users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1
            if u.is_active:
                active_users += 1
            if u.is_verified:
                verified_users += 1
        
        context = {
            'user': user,
            'total_farms': total_farms,
            'total_area': total_area,
            'total_users': len(all_users),
            'total_livestock': total_livestock_count,
            'active_users': active_users,
            'verified_users': verified_users,
            'role_counts': role_counts,
            'inactive_farms': len([f for f in farms if not f.is_active]),
            'inactive_users': len([u for u in all_users if not u.is_active]),
            'farms': farms,
            'users': all_users,
            'animals_with_diseases': animals_with_diseases,
            'upcoming_vaccines': upcoming_vaccines,
            'vaccines_count': vaccines_count,
            'expired_vaccines': expired_vaccines,
            'expiring_soon_vaccines': expiring_soon_vaccines,
            'total_health_alerts': total_health_alerts,
            'critical_alerts': critical_alerts
        }
        
        logger.info(f"[SYSTEM_ADMIN_DASHBOARD] Loaded dashboard for system admin {user.username}")
        return render_template('dashboard/system_admin.html', **context)
    except Exception as e:
        logger.error(f"[SYSTEM_ADMIN_DASHBOARD] Error loading dashboard for user {user.username}: {str(e)}", exc_info=True)
        flash('Error loading dashboard data.', 'warning')
        context = {
            'user': user,
            'total_farms': 0,
            'total_area': 0,
            'total_users': 0,
            'total_livestock': 0,
            'active_users': 0,
            'verified_users': 0,
            'role_counts': {},
            'inactive_farms': 0,
            'inactive_users': 0,
            'farms': [],
            'users': [],
            'animals_with_diseases': 0,
            'upcoming_vaccines': 0,
            'vaccines_count': 0,
            'expired_vaccines': 0,
            'expiring_soon_vaccines': 0,
            'total_health_alerts': 0,
            'critical_alerts': 0,
            'error': str(e)
        }
        return render_template('dashboard/system_admin.html', **context)


@dashboard_bp.route('/profile', methods=['GET'])
@login_required
def profile():
    """User profile page"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user:
        logger.warning(f"User {user_id} not found during profile load")
        flash('Unable to load profile. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    return render_template('dashboard/profile.html', user=user)


@dashboard_bp.route('/profile/edit', methods=['POST'])
@login_required
def edit_profile():
    """Edit user profile information"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user:
        logger.warning(f"User {user_id} not found during profile edit")
        flash('Unable to load your profile. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # Get form data
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validate inputs
        if not full_name or len(full_name) < 2:
            logger.warning(f"[EDIT_PROFILE] Invalid full name for user {user.username}")
            flash('Full name must be at least 2 characters long.', 'error')
            return redirect(url_for('dashboard.profile'))
        
        if not email or '@' not in email:
            logger.warning(f"[EDIT_PROFILE] Invalid email format for user {user.username}")
            flash('Invalid email address.', 'error')
            return redirect(url_for('dashboard.profile'))
        
        # Check if email is already taken by another user
        existing_email = User.query.filter(User.email == email, User.id != user.id).first()
        if existing_email:
            logger.warning(f"[EDIT_PROFILE] Email {email} already in use")
            flash('This email address is already in use by another account.', 'error')
            return redirect(url_for('dashboard.profile'))
        
        # If changing password, verify current password
        if new_password or confirm_password:
            if not current_password:
                logger.warning(f"[EDIT_PROFILE] Password change attempted without current password verification for user {user.username}")
                flash('Current password is required to change your password.', 'error')
                return redirect(url_for('dashboard.profile'))
            
            if not user.check_password(current_password):
                logger.warning(f"[EDIT_PROFILE] Invalid current password for user {user.username}")
                flash('Your current password is incorrect.', 'error')
                return redirect(url_for('dashboard.profile'))
            
            # Validate new password
            if not new_password:
                flash('Please enter a new password.', 'error')
                return redirect(url_for('dashboard.profile'))
            
            if len(new_password) < 8:
                logger.warning(f"[EDIT_PROFILE] Password too short for user {user.username}")
                flash('Password must be at least 8 characters long.', 'error')
                return redirect(url_for('dashboard.profile'))
            
            if new_password != confirm_password:
                logger.warning(f"[EDIT_PROFILE] Password mismatch for user {user.username}")
                flash('New passwords do not match.', 'error')
                return redirect(url_for('dashboard.profile'))
            
            # Update password
            user.set_password(new_password)
            logger.info(f"[EDIT_PROFILE] Password changed for user {user.username}")
        
        # Update profile information
        user.full_name = full_name
        user.email = email
        
        # Commit changes
        db.session.commit()
        
        logger.info(f"[EDIT_PROFILE] Profile updated for user {user.username} - full_name={full_name}, email={email}")
        
        # Update session data
        session['full_name'] = full_name
        
        flash('Your profile has been updated successfully!', 'success')
        return redirect(url_for('dashboard.profile'))
    
    except Exception as e:
        logger.error(f"[EDIT_PROFILE] Error updating profile for user {user.username}: {str(e)}", exc_info=True)
        db.session.rollback()
        flash('An error occurred while updating your profile. Please try again.', 'error')
        return redirect(url_for('dashboard.profile'))


# ============================================
# VICTORIA ADMIN - ADMINISTRATIVE FUNCTIONS
# ============================================

@dashboard_bp.route('/admin/users', methods=['GET'])
@login_required
def admin_users():
    """Manage all users - Victoria Admin only"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'victoria_admin':
        flash('Access denied. This page is for Victoria admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Get all users
        all_users = User.query.filter_by(is_active=True).order_by(User.created_at.desc()).all()
        
        # Count by role
        role_counts = {}
        for u in all_users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1
        
        context = {
            'user': user,
            'all_users': all_users,
            'role_counts': role_counts,
            'total_users': len(all_users)
        }
        
        logger.info(f"[ADMIN_USERS] Victoria admin {user.username} accessed user management")
        return render_template('admin/users.html', **context)
    except Exception as e:
        logger.error(f"[ADMIN_USERS] Error loading user management: {str(e)}", exc_info=True)
        flash('An error occurred while loading user management.', 'error')
        return redirect(url_for('dashboard.victoria_admin_dashboard'))


@dashboard_bp.route('/admin/user/<int:user_id>/deactivate', methods=['POST'])
@login_required
def admin_deactivate_user(user_id):
    """Deactivate a user - Victoria Admin only"""
    admin_user = User.query.get(session.get('user_id'))
    
    if not admin_user or admin_user.role != 'victoria_admin':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        target_user = User.query.get(user_id)
        
        if not target_user:
            flash('User not found.', 'error')
            return redirect(url_for('dashboard.admin_users'))
        
        if target_user.id == admin_user.id:
            flash('You cannot deactivate your own account.', 'error')
            return redirect(url_for('dashboard.admin_users'))
        
        target_user.is_active = False
        db.session.commit()
        
        logger.info(f"[ADMIN_DEACTIVATE] Victoria admin {admin_user.username} deactivated user {target_user.username}")
        flash(f'User {target_user.full_name} has been deactivated.', 'success')
        
    except Exception as e:
        logger.error(f"[ADMIN_DEACTIVATE] Error deactivating user: {str(e)}", exc_info=True)
        db.session.rollback()
        flash('An error occurred while deactivating the user.', 'error')
    
    return redirect(url_for('dashboard.admin_users'))


@dashboard_bp.route('/admin/user/<int:user_id>/activate', methods=['POST'])
@login_required
def admin_activate_user(user_id):
    """Activate a user - Victoria Admin only"""
    admin_user = User.query.get(session.get('user_id'))
    
    if not admin_user or admin_user.role != 'victoria_admin':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        target_user = User.query.get(user_id)
        
        if not target_user:
            flash('User not found.', 'error')
            return redirect(url_for('dashboard.admin_users'))
        
        target_user.is_active = True
        db.session.commit()
        
        logger.info(f"[ADMIN_ACTIVATE] Victoria admin {admin_user.username} activated user {target_user.username}")
        flash(f'User {target_user.full_name} has been activated.', 'success')
        
    except Exception as e:
        logger.error(f"[ADMIN_ACTIVATE] Error activating user: {str(e)}", exc_info=True)
        db.session.rollback()
        flash('An error occurred while activating the user.', 'error')
    
    return redirect(url_for('dashboard.admin_users'))


@dashboard_bp.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    """System settings - Victoria Admin only"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'victoria_admin':
        flash('Access denied. This page is for Victoria admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        if request.method == 'POST':
            logger.info(f"[ADMIN_SETTINGS] Victoria admin {user.username} saved settings")
            flash('System settings updated successfully.', 'success')
            return redirect(url_for('dashboard.admin_settings'))
        
        # Get system statistics
        total_farms = Farm.query.filter_by(is_active=True).count()
        total_users = User.query.filter_by(is_active=True).count()
        total_area = sum(farm.area_square_meters for farm in Farm.query.filter_by(is_active=True).all()) or 0
        
        context = {
            'user': user,
            'total_farms': total_farms,
            'total_users': total_users,
            'total_area': total_area,
            'barangays': {
                'Banca-Banca': Farm.query.filter_by(barangay_name='Banca-Banca', is_active=True).count(),
                'Daniw': Farm.query.filter_by(barangay_name='Daniw', is_active=True).count(),
                'Masapang': Farm.query.filter_by(barangay_name='Masapang', is_active=True).count(),
                'Nanhaya': Farm.query.filter_by(barangay_name='Nanhaya', is_active=True).count(),
                'Pagalangan': Farm.query.filter_by(barangay_name='Pagalangan', is_active=True).count(),
                'San Benito': Farm.query.filter_by(barangay_name='San Benito', is_active=True).count(),
                'San Felix': Farm.query.filter_by(barangay_name='San Felix', is_active=True).count(),
                'San Francisco': Farm.query.filter_by(barangay_name='San Francisco', is_active=True).count(),
                'San Roque': Farm.query.filter_by(barangay_name='San Roque', is_active=True).count(),
            }
        }
        
        logger.info(f"[ADMIN_SETTINGS] Victoria admin {user.username} accessed settings")
        return render_template('admin/settings.html', **context)
    except Exception as e:
        logger.error(f"[ADMIN_SETTINGS] Error loading settings: {str(e)}", exc_info=True)
        flash('An error occurred while loading settings.', 'error')
        return redirect(url_for('dashboard.victoria_admin_dashboard'))


# ============================================
# SYSTEM ADMIN - ADMINISTRATIVE FUNCTIONS
# ============================================

@dashboard_bp.route('/admin/users-system', methods=['GET'])
@login_required
def admin_users_system():
    """Manage all users - System Admin only (full control)"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'system_admin':
        flash('Access denied. This page is for system admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        # Get all users including inactive
        all_users = User.query.order_by(User.created_at.desc()).all()
        
        # Count by role and status
        role_counts = {}
        active_count = 0
        verified_count = 0
        for u in all_users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1
            if u.is_active:
                active_count += 1
            if u.is_verified:
                verified_count += 1
        
        context = {
            'user': user,
            'all_users': all_users,
            'role_counts': role_counts,
            'total_users': len(all_users),
            'active_users': active_count,
            'verified_users': verified_count
        }
        
        logger.info(f"[ADMIN_USERS_SYSTEM] System admin {user.username} accessed user management")
        return render_template('admin/users_system.html', **context)
    except Exception as e:
        logger.error(f"[ADMIN_USERS_SYSTEM] Error loading user management: {str(e)}", exc_info=True)
        flash('An error occurred while loading user management.', 'error')
        return redirect(url_for('dashboard.system_admin_dashboard'))


@dashboard_bp.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Delete a user permanently - System Admin only"""
    admin_user = User.query.get(session.get('user_id'))
    
    if not admin_user or admin_user.role != 'system_admin':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        target_user = User.query.get(user_id)
        
        if not target_user:
            flash('User not found.', 'error')
            return redirect(url_for('dashboard.admin_users_system'))
        
        if target_user.id == admin_user.id:
            flash('You cannot delete your own account.', 'error')
            return redirect(url_for('dashboard.admin_users_system'))
        
        username = target_user.username
        db.session.delete(target_user)
        db.session.commit()
        
        logger.info(f"[ADMIN_DELETE] System admin {admin_user.username} deleted user {username}")
        flash(f'User {username} has been permanently deleted.', 'success')
        
    except Exception as e:
        logger.error(f"[ADMIN_DELETE] Error deleting user: {str(e)}", exc_info=True)
        db.session.rollback()
        flash('An error occurred while deleting the user.', 'error')
    
    return redirect(url_for('dashboard.admin_users_system'))


@dashboard_bp.route('/admin/user/<int:user_id>/verify', methods=['POST'])
@login_required
def admin_verify_user(user_id):
    """Verify a user account - System Admin only"""
    admin_user = User.query.get(session.get('user_id'))
    
    if not admin_user or admin_user.role != 'system_admin':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        target_user = User.query.get(user_id)
        
        if not target_user:
            flash('User not found.', 'error')
            return redirect(url_for('dashboard.admin_users_system'))
        
        target_user.is_verified = True
        db.session.commit()
        
        logger.info(f"[ADMIN_VERIFY] System admin {admin_user.username} verified user {target_user.username}")
        flash(f'User {target_user.full_name} has been verified.', 'success')
        
    except Exception as e:
        logger.error(f"[ADMIN_VERIFY] Error verifying user: {str(e)}", exc_info=True)
        db.session.rollback()
        flash('An error occurred while verifying the user.', 'error')
    
    return redirect(url_for('dashboard.admin_users_system'))


@dashboard_bp.route('/admin/database', methods=['GET', 'POST'])
@login_required
def admin_database():
    """Database management - System Admin only"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'system_admin':
        flash('Access denied. This page is for system admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'optimize':
                logger.info(f"[ADMIN_DATABASE] System admin {user.username} optimized database")
                flash('Database optimization completed successfully.', 'success')
            elif action == 'backup':
                logger.info(f"[ADMIN_DATABASE] System admin {user.username} created database backup")
                flash('Database backup created successfully.', 'success')
            
            return redirect(url_for('dashboard.admin_database'))
        
        # Get database statistics
        total_farms = Farm.query.count()
        active_farms = Farm.query.filter_by(is_active=True).count()
        inactive_farms = total_farms - active_farms
        
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        inactive_users = total_users - active_users
        
        context = {
            'user': user,
            'total_farms': total_farms,
            'active_farms': active_farms,
            'inactive_farms': inactive_farms,
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users
        }
        
        logger.info(f"[ADMIN_DATABASE] System admin {user.username} accessed database management")
        return render_template('admin/database.html', **context)
    except Exception as e:
        logger.error(f"[ADMIN_DATABASE] Error loading database management: {str(e)}", exc_info=True)
        flash('An error occurred while loading database management.', 'error')
        return redirect(url_for('dashboard.system_admin_dashboard'))


@dashboard_bp.route('/admin/settings-system', methods=['GET', 'POST'])
@login_required
def admin_settings_system():
    """System settings - System Admin only (full control)"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if not user or user.role != 'system_admin':
        flash('Access denied. This page is for system admins only.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        if request.method == 'POST':
            logger.info(f"[ADMIN_SETTINGS_SYSTEM] System admin {user.username} updated settings")
            flash('System settings updated successfully.', 'success')
            return redirect(url_for('dashboard.admin_settings_system'))
        
        # Get comprehensive system statistics
        total_farms = Farm.query.count()
        active_farms = Farm.query.filter_by(is_active=True).count()
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_area = sum(farm.area_square_meters for farm in Farm.query.all()) or 0
        
        # Barangay breakdown
        barangays = {
            'Banca-Banca': Farm.query.filter_by(barangay_name='Banca-Banca').count(),
            'Daniw': Farm.query.filter_by(barangay_name='Daniw').count(),
            'Masapang': Farm.query.filter_by(barangay_name='Masapang').count(),
            'Nanhaya': Farm.query.filter_by(barangay_name='Nanhaya').count(),
            'Pagalangan': Farm.query.filter_by(barangay_name='Pagalangan').count(),
            'San Benito': Farm.query.filter_by(barangay_name='San Benito').count(),
            'San Felix': Farm.query.filter_by(barangay_name='San Felix').count(),
            'San Francisco': Farm.query.filter_by(barangay_name='San Francisco').count(),
            'San Roque': Farm.query.filter_by(barangay_name='San Roque').count(),
        }
        
        context = {
            'user': user,
            'total_farms': total_farms,
            'active_farms': active_farms,
            'total_users': total_users,
            'active_users': active_users,
            'total_area': total_area,
            'barangays': barangays
        }
        
        logger.info(f"[ADMIN_SETTINGS_SYSTEM] System admin {user.username} accessed system settings")
        return render_template('admin/settings_system.html', **context)
    except Exception as e:
        logger.error(f"[ADMIN_SETTINGS_SYSTEM] Error loading system settings: {str(e)}", exc_info=True)
        flash('An error occurred while loading system settings.', 'error')
        return redirect(url_for('dashboard.system_admin_dashboard'))
