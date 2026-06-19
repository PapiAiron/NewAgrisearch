from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from app import db
from app.models.crop import Crop, CropGrowthRecord
from app.models.farm import Farm
from app.models.user import User
from app.models.supply import FarmSupplyUsage
from datetime import datetime, date
from functools import wraps

crop_bp = Blueprint('crop', __name__, url_prefix='/crop')

def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def farmer_or_staff_required(f):
    """Decorator to check if user is farmer or staff"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if user.role not in ['farmer', 'victoria_admin', 'system_admin']:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

# ===== CROP API ENDPOINTS =====

@crop_bp.route('/api/active', methods=['GET'])
@login_required
def get_active_crops():
    """Get active crops for a specific farm (API endpoint for supply usage form)"""
    user = User.query.get(session['user_id'])
    farm_id = request.args.get('farm_id', type=int)
    
    if not farm_id:
        return jsonify({'error': 'farm_id required'}), 400
    
    # Get the farm
    farm = Farm.query.get(farm_id)
    if not farm:
        return jsonify({'error': 'Farm not found'}), 404
    
    # Permission check: farmer can only see their own farms, officers see their barangay
    if user.role == 'farmer':
        if farm not in user.farms:
            return jsonify({'error': 'Unauthorized'}), 403
    elif user.role not in ['victoria_admin', 'system_admin']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get active crops (status='active') for this farm
    active_crops = Crop.query.filter(
        Crop.farm_id == farm_id,
        Crop.status == 'active'
    ).order_by(Crop.crop_type, Crop.id).all()
    
    crops_list = [
        {
            'id': crop.id,
            'name': f"{crop.crop_type} (Field {crop.id})" if not crop.notes else f"{crop.crop_type} - {crop.notes}",
            'crop_type': crop.crop_type,
            'status': crop.status
        }
        for crop in active_crops
    ]
    
    return jsonify(crops_list)

# ===== CROP ROUTES =====

@crop_bp.route('/list', methods=['GET'])
@login_required
@farmer_or_staff_required
def list_crops():
    """List all crops with filtering"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Farmers see only their own farms' crops
    if user.role == 'farmer':
        farms = user.farms
        query = Crop.query.filter(Crop.farm_id.in_([f.id for f in farms]))
    elif user.role in ['victoria_admin', 'system_admin']:
        # Admins see all crops
        query = Crop.query
    else:
        query = Crop.query.filter(False)
    
    # Get filter parameters
    crop_type_filter = request.args.get('crop_type', '')
    status_filter = request.args.get('status', '')
    stage_filter = request.args.get('stage', '')
    farm_id_filter = request.args.get('farm_id', '')
    search_query = request.args.get('search', '').strip()
    
    # Apply search filter
    if search_query:
        query = query.filter(
            db.or_(
                Crop.crop_type.ilike(f'%{search_query}%'),
                Crop.notes.ilike(f'%{search_query}%'),
                Farm.name.ilike(f'%{search_query}%')
            )
        )
    
    # Apply crop type filter
    if crop_type_filter and crop_type_filter != '':
        query = query.filter_by(crop_type=crop_type_filter)
    
    # Apply status filter
    if status_filter and status_filter != '':
        query = query.filter_by(status=status_filter)
    
    # Apply growth stage filter
    if stage_filter and stage_filter != '':
        query = query.filter_by(current_growth_stage=stage_filter)
    
    # Apply farm filter (for admin views)
    if farm_id_filter and farm_id_filter != '' and user.role in ['victoria_admin', 'system_admin']:
        query = query.filter_by(farm_id=int(farm_id_filter))
    
    crop_list = query.all()
    
    # Get available filter options
    if user.role == 'farmer':
        farm_ids = [f.id for f in farms]
        farm_options = farms
        crop_type_options = sorted(list(set([c.crop_type for c in Crop.query.filter(Crop.farm_id.in_(farm_ids)).all()])))
        stage_options = sorted(list(set([c.current_growth_stage for c in Crop.query.filter(Crop.farm_id.in_(farm_ids)).all()])))
    else:
        farm_options = Farm.query.all()
        all_crops = Crop.query.all()
        crop_type_options = sorted(list(set([c.crop_type for c in all_crops])))
        stage_options = sorted(list(set([c.current_growth_stage for c in all_crops])))
    
    # Status options are static
    status_options = ['active', 'harvested', 'failed', 'abandoned']
    
    return render_template('crop/list.html', crops=crop_list, user=user, 
                         crop_type_options=crop_type_options,
                         status_options=status_options,
                         stage_options=stage_options,
                         farm_options=farm_options,
                         active_crop_type=crop_type_filter,
                         active_status=status_filter,
                         active_stage=stage_filter,
                         active_farm=farm_id_filter,
                         search_query=search_query)

@crop_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_crop():
    """Create a new crop"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Only farmers can create crops
    if user.role != 'farmer':
        flash('Only farmers can create crops', 'error')
        return redirect(url_for('crop.list_crops'))
    
    # Get available farms
    farms = user.farms
    
    if request.method == 'POST':
        try:
            farm_id = request.form.get('farm_id', type=int)
            crop_type = request.form.get('crop_type')
            planting_date = request.form.get('planting_date')
            expected_harvest_date = request.form.get('expected_harvest_date')
            notes = request.form.get('notes')
            
            # Validate farm ownership for farmers
            if user.role == 'farmer':
                farm = Farm.query.filter_by(id=farm_id, owner_id=user_id).first()
                if not farm:
                    flash('You do not have permission to add crops to this farm', 'error')
                    return redirect(url_for('crop.list_crops'))
            
            crop = Crop(
                farm_id=farm_id,
                crop_type=crop_type,
                planting_date=datetime.strptime(planting_date, '%Y-%m-%d').date(),
                expected_harvest_date=datetime.strptime(expected_harvest_date, '%Y-%m-%d').date() if expected_harvest_date else None,
                notes=notes,
                status='active'
            )
            
            db.session.add(crop)
            db.session.commit()
            
            flash(f'Crop "{crop_type}" added successfully', 'success')
            return redirect(url_for('crop.view_crop', crop_id=crop.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating crop: {str(e)}', 'error')
            return redirect(url_for('crop.list_crops'))
    
    return render_template('crop/create.html', farms=farms, user=user)

@crop_bp.route('/<int:crop_id>', methods=['GET'])
@login_required
@farmer_or_staff_required
def view_crop(crop_id):
    """View crop details with growth timeline"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    crop = Crop.query.get_or_404(crop_id)
    
    # Verify access for farmers
    if user.role == 'farmer' and crop.farm.owner_id != user_id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('crop.list_crops'))
    
    growth_records = CropGrowthRecord.query.filter_by(crop_id=crop_id).order_by(CropGrowthRecord.record_date).all()

    # Get supply usage records applied to this crop
    supply_usages = FarmSupplyUsage.query.filter_by(
        related_model='crop',
        related_id=crop_id
    ).order_by(FarmSupplyUsage.usage_date.desc()).all()
    
    return render_template('crop/detail.html', crop=crop, growth_records=growth_records, supply_usages=supply_usages, user=user)

@crop_bp.route('/<int:crop_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_crop(crop_id):
    """Edit crop information"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    crop = Crop.query.get_or_404(crop_id)
    
    # Only farmers can edit crops
    if user.role != 'farmer':
        flash('Only farmers can edit crops', 'error')
        return redirect(url_for('crop.list_crops'))
    
    # Verify farm ownership
    if crop.farm.owner_id != user_id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('crop.list_crops'))
    
    if request.method == 'POST':
        try:
            crop.crop_type = request.form.get('crop_type')
            crop.planting_date = datetime.strptime(request.form.get('planting_date'), '%Y-%m-%d').date()
            expected_harvest_date = request.form.get('expected_harvest_date')
            crop.expected_harvest_date = datetime.strptime(expected_harvest_date, '%Y-%m-%d').date() if expected_harvest_date else None
            crop.current_growth_stage = request.form.get('current_growth_stage')
            crop.notes = request.form.get('notes')
            crop.status = request.form.get('status')
            
            yield_amount = request.form.get('yield_amount')
            if yield_amount:
                crop.yield_amount = float(yield_amount)
            
            crop.yield_unit = request.form.get('yield_unit', 'kg')
            crop.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Crop updated successfully', 'success')
            return redirect(url_for('crop.view_crop', crop_id=crop.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating crop: {str(e)}', 'error')
    
    growth_stages = ['seedling', 'vegetative', 'flowering', 'fruiting', 'mature']
    statuses = ['active', 'harvested', 'failed', 'abandoned']
    
    return render_template('crop/edit.html', crop=crop, growth_stages=growth_stages, statuses=statuses, user=user)

@crop_bp.route('/<int:crop_id>/delete', methods=['POST'])
@login_required
def delete_crop(crop_id):
    """Delete a crop"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    crop = Crop.query.get_or_404(crop_id)
    
    # Only farmers can delete crops
    if user.role != 'farmer':
        flash('Only farmers can delete crops', 'error')
        return redirect(url_for('crop.list_crops'))
    
    # Verify farm ownership
    if crop.farm.owner_id != user_id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('crop.list_crops'))
    
    try:
        db.session.delete(crop)
        db.session.commit()
        flash('Crop deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting crop: {str(e)}', 'error')
    
    return redirect(url_for('crop.list_crops'))

@crop_bp.route('/<int:crop_id>/add-record', methods=['POST'])
@login_required
@farmer_or_staff_required
def add_growth_record(crop_id):
    """Add a growth record for a crop"""
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    crop = Crop.query.get_or_404(crop_id)
    
    # Verify access for farmers
    if user.role == 'farmer' and crop.farm.owner_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        record_date = request.form.get('record_date')
        growth_stage = request.form.get('growth_stage')
        height_cm = request.form.get('height_cm')
        health_status = request.form.get('health_status', 'healthy')
        notes = request.form.get('notes')
        
        record = CropGrowthRecord(
            crop_id=crop_id,
            record_date=datetime.strptime(record_date, '%Y-%m-%d').date() if record_date else date.today(),
            growth_stage=growth_stage,
            height_cm=float(height_cm) if height_cm else None,
            health_status=health_status,
            notes=notes
        )
        
        db.session.add(record)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Growth record added successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

