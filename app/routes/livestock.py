"""
Livestock management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app import db
from app.models.user import User
from app.models.farm import Farm
from app.models.livestock import Livestock, NutritionRecord, HealthRecord, ProductivityRecord, LivestockEvent, LivestockWeightLog
from app.models.health import VaccineInventory
from app.models.supply import Supply, FarmSupplyUsage, FarmSupplyInventory
from app.models.distribution import DistributionRequest, DistributionRecord
from functools import wraps
from datetime import datetime, timedelta
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

livestock_bp = Blueprint('livestock', __name__, url_prefix='/livestock')

# Animal types
ANIMAL_TYPES = {
    'cattle': 'Cattle',
    'pig': 'Pig',
    'goat': 'Goat',
    'chicken': 'Chicken',
    'duck': 'Duck',
    'turkey': 'Turkey',
    'carabao': 'Carabao',
    'rabbit': 'Rabbit',
    'fish': 'Fish',
    'other': 'Other'
}

RECORD_TYPES = {
    'vaccine': 'Vaccine',
    'vitamin': 'Vitamin',
    'medication': 'Medication',
    'checkup': 'Checkup',
    'treatment': 'Treatment',
    'deworming': 'Deworming'
}

PRODUCTIVITY_TYPES = {
    'eggs_laid': 'Eggs Laid',
    'milk_produced': 'Milk Produced',
    'weight_gain': 'Weight Gain',
    'offspring': 'Offspring',
    'meat_produced': 'Meat Produced',
    'wool_produced': 'Wool Produced'
}

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@livestock_bp.route('/api/active', methods=['GET'])
@login_required
def get_active_livestock():
    """Get active livestock for a specific farm (API endpoint for supply usage form)"""
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
    
    # Get active livestock (status='active') for this farm
    active_livestock = Livestock.query.filter(
        Livestock.farm_id == farm_id,
        Livestock.status == 'active'
    ).order_by(Livestock.animal_type, Livestock.unique_id).all()
    
    livestock_list = [
        {
            'id': animal.id,
            'name': f"{animal.unique_id or f'ID-{animal.id}'} ({ANIMAL_TYPES.get(animal.animal_type, animal.animal_type)})",
            'animal_type': animal.animal_type,
            'status': animal.status
        }
        for animal in active_livestock
    ]
    
    return jsonify(livestock_list)


@livestock_bp.route('/api/vaccines', methods=['GET'])
@login_required
def get_available_vaccines():
    """Get available vaccines for a farm via API - from both farm inventory and supply distributions"""
    try:
        farm_id = request.args.get('farm_id', type=int)
        if not farm_id:
            return jsonify({'error': 'farm_id required'}), 400
        
        user = User.query.get(session['user_id'])
        farm = Farm.query.get_or_404(farm_id)
        
        logger.info(f"[API] Vaccine request - User: {user.username} ({user.role}), Farm: {farm.name} (ID: {farm_id})")
        
        # Check permissions
        if user.role == 'farmer' and farm.owner_id != user.id:
            logger.warning(f"[API] Access denied - Farmer {user.username} trying to access farm {farm.name}")
            return jsonify({'error': 'Access denied'}), 403
        
        vaccines_list = []
        
        # 1. Get farm-specific vaccine inventory
        # NOTE: quantity_remaining is a property, not a column, so we filter on the calculation
        farm_vaccines = VaccineInventory.query.filter(
            VaccineInventory.farm_id == farm_id,
            VaccineInventory.is_active == True,
            (VaccineInventory.quantity_units - VaccineInventory.quantity_used) > 0  # Calculate remaining
        ).order_by(VaccineInventory.vaccine_name).all()
        
        logger.info(f"[API] Farm vaccines query: farm_id={farm_id}, is_active=True, (quantity_units - quantity_used) > 0")
        logger.info(f"[API] Farm vaccines found: {len(farm_vaccines)}")
        for v in farm_vaccines:
            logger.info(f"[API]   - {v.vaccine_name} (ID: {v.id}, Qty: {v.quantity_remaining})")
            vaccines_list.append({
                'id': f'farm_{v.id}',  # Prefix to identify source
                'vaccine_name': v.vaccine_name,
                'vaccine_code': v.vaccine_code,
                'quantity_remaining': v.quantity_remaining,
                'unit_type': v.unit_type,
                'expiry_date': v.expiry_date.strftime('%Y-%m-%d') if v.expiry_date else None,
                'cost_per_unit': v.cost_per_unit,
                'is_expired': v.is_expired,
                'source': 'farm_inventory',
                'source_id': v.id
            })
        
        # 2. Get vaccines from verified distributions (supply inventory)
        supply_vaccines = db.session.query(
            DistributionRecord,
            DistributionRequest,
            Supply
        ).join(
            DistributionRequest, DistributionRecord.request_id == DistributionRequest.id
        ).join(
            Supply, Supply.name == DistributionRequest.supply_name
        ).filter(
            DistributionRequest.farm_id == farm_id,
            DistributionRequest.supply_type == 'vaccine',
            DistributionRecord.status == 'verified',
            DistributionRecord.quantity_distributed > 0,
            Supply.supply_type == 'vaccine'
        ).all()
        
        for dist_record, dist_request, supply in supply_vaccines:
            vaccines_list.append({
                'id': f'dist_{dist_record.id}',  # Prefix to identify source
                'vaccine_name': dist_request.supply_name,
                'vaccine_code': dist_request.supply_name,  # Use supply name as code
                'quantity_remaining': dist_record.quantity_distributed,  # Use distributed quantity
                'unit_type': dist_request.unit,
                'expiry_date': None,  # Supplies don't have expiry tracking
                'cost_per_unit': supply.unit_cost or 0,
                'is_expired': False,
                'source': 'supply_distribution',
                'source_id': dist_record.id
            })
        
        # Sort by vaccine name
        vaccines_list.sort(key=lambda x: x['vaccine_name'])
        
        logger.info(f"[API] Total vaccines returned: {len(vaccines_list)}")
        return jsonify(vaccines_list)
        
    except Exception as e:
        logger.error(f"[API] Error fetching vaccines: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@livestock_bp.route('/', methods=['GET'])
@login_required
def list_livestock():
    """List all livestock for user's farms"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        logger.debug(f"Loading livestock for user {user.username} with role {user.role}")
        
        # Get farm filter if provided
        farm_id = request.args.get('farm_id', type=int)
        animal_type = request.args.get('animal_type', '')
        status = request.args.get('status', 'active')
        search_query = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        query = Livestock.query
        logger.debug(f"Initial query created")
        
        # Filter by user's farms
        if user.role == 'farmer':
            # For farmers, get farms directly from database filtered by owner_id
            farm_ids = db.session.query(Farm.id).filter(Farm.owner_id == user.id).all()
            farm_ids = [f[0] for f in farm_ids]
            logger.debug(f"Farmer {user.username} has farms: {farm_ids}")
            if farm_ids:
                query = query.filter(Livestock.farm_id.in_(farm_ids))
            else:
                query = query.filter(False)  # No farms, show nothing
        elif user.role not in ['system_admin', 'victoria_admin']:
            logger.debug(f"User {user.username} with role {user.role} sees all livestock")
            pass
        
        # Apply filters
        if farm_id:
            query = query.filter(Livestock.farm_id == farm_id)
        if animal_type:
            query = query.filter(Livestock.animal_type == animal_type)
        if status == 'ready':
            # Filter to active only; readiness computed after query
            query = query.filter(Livestock.status == 'active')
        elif status:
            query = query.filter(Livestock.status == status)
        
        # Apply search filter
        if search_query:
            query = query.filter(
                db.or_(
                    Livestock.animal_type.ilike(f'%{search_query}%'),
                    Livestock.unique_id.ilike(f'%{search_query}%'),
                    Livestock.breed.ilike(f'%{search_query}%')
                )
            )
        
        logger.debug(f"Executing livestock query")
        if status == 'ready':
            # 'ready' is a Python property - fetch all active, filter, then paginate manually
            all_active = query.order_by(Livestock.created_at.desc()).all()
            all_ready = [l for l in all_active if l.is_ready_for_sale]
            total_ready = len(all_ready)
            start = (page - 1) * per_page
            livestock = all_ready[start: start + per_page]

            class _Pagination:
                def __init__(self, items, total, page, per_page):
                    self.items = items
                    self.total = total
                    self.page = page
                    self.per_page = per_page
                    self.pages = max(1, -(-total // per_page))  # ceiling div
                    self.has_prev = page > 1
                    self.has_next = page < self.pages
                    self.prev_num = page - 1
                    self.next_num = page + 1
            pagination = _Pagination(livestock, total_ready, page, per_page)
        else:
            pagination = query.order_by(Livestock.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
            livestock = pagination.items
        logger.debug(f"Found {pagination.total} livestock records ({len(livestock)} on page {page})")
        
        # Get farms to display
        if user.role == 'farmer':
            farms = db.session.query(Farm).filter(Farm.owner_id == user.id).all()
        else:
            farms = Farm.query.all()
        logger.debug(f"Loaded {len(farms)} farms")
        
        # Calculate statistics
        total_animals = sum([l.count or 1 for l in livestock]) if livestock else 0
        by_type = {}
        for animal in livestock:
            type_name = animal.animal_type
            by_type[type_name] = by_type.get(type_name, 0) + (animal.count or 1)
        
        logger.debug(f"Statistics calculated: {total_animals} total animals, types: {by_type}")
        
        # Get upcoming vaccine alerts
        alerts = []
        if livestock:
            try:
                livestock_ids = [l.id for l in livestock]
                logger.debug(f"Fetching vaccine alerts for {len(livestock_ids)} livestock")
                alerts = HealthRecord.query.filter(
                    HealthRecord.livestock_id.in_(livestock_ids),
                    HealthRecord.record_type == 'vaccine',
                    HealthRecord.next_due_date != None,
                    HealthRecord.next_due_date <= datetime.utcnow() + timedelta(days=7),
                    HealthRecord.next_due_date > datetime.utcnow()
                ).all()
                logger.debug(f"Found {len(alerts)} upcoming vaccine alerts")
            except Exception as alert_error:
                logger.error(f"Error fetching vaccine alerts: {str(alert_error)}", exc_info=True)
                alerts = []
        
        logger.info(f"Successfully loaded livestock page for user {user.username}")
        return render_template('livestock/list.html',
                             livestock=livestock,
                             farms=farms,
                             animal_types=ANIMAL_TYPES,
                             total_animals=total_animals,
                             by_type=by_type,
                             alerts=alerts,
                             pagination=pagination,
                             user=user,
                             search_query=search_query,
                             active_farm=farm_id,
                             active_animal=animal_type,
                             active_status=status)
    except Exception as e:
        logger.error(f"Error listing livestock: {str(e)}", exc_info=True)
        flash(f'Error loading livestock data: {str(e)}', 'error')
        return redirect(url_for('dashboard.index'))


@livestock_bp.route('/<int:livestock_id>', methods=['GET'])
@login_required
def view_livestock(livestock_id):
    """View livestock details"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        # Get related data
        nutrition = NutritionRecord.query.filter_by(livestock_id=livestock_id, is_active=True).all()
        health = HealthRecord.query.filter_by(livestock_id=livestock_id).order_by(HealthRecord.date_administered.desc()).all()
        productivity = ProductivityRecord.query.filter_by(livestock_id=livestock_id).order_by(ProductivityRecord.record_date.desc()).limit(30).all()
        
        # Get upcoming vaccines
        upcoming_vaccines = HealthRecord.query.filter(
            HealthRecord.livestock_id == livestock_id,
            HealthRecord.record_type == 'vaccine',
            HealthRecord.next_due_date != None,
            HealthRecord.next_due_date > datetime.utcnow()
        ).order_by(HealthRecord.next_due_date).all()

        # Get supply usage records applied to this livestock
        supply_usages = FarmSupplyUsage.query.filter_by(
            related_model='livestock',
            related_id=livestock_id
        ).order_by(FarmSupplyUsage.usage_date.desc()).all()

        # Get events (deaths, sales, transfers)
        events = LivestockEvent.query.filter_by(livestock_id=livestock_id).order_by(LivestockEvent.event_date.desc()).all()

        # Get weight history
        weight_logs = LivestockWeightLog.query.filter_by(livestock_id=livestock_id).order_by(LivestockWeightLog.weighed_at.desc()).all()

        # Compute event summary totals
        total_revenue = sum(e.total_revenue or 0 for e in events if e.event_type == 'sale')
        total_deaths  = sum(e.count_affected for e in events if e.event_type == 'death')

        return render_template('livestock/detail.html',
                             livestock=livestock,
                             nutrition=nutrition,
                             health=health,
                             productivity=productivity,
                             upcoming_vaccines=upcoming_vaccines,
                             supply_usages=supply_usages,
                             events=events,
                             weight_logs=weight_logs,
                             total_revenue=total_revenue,
                             total_deaths=total_deaths,
                             record_types=RECORD_TYPES,
                             productivity_types=PRODUCTIVITY_TYPES,
                             user=user)
    except Exception as e:
        logger.error(f"Error viewing livestock {livestock_id}: {str(e)}", exc_info=True)
        flash(f'Error loading livestock details: {str(e)}', 'error')
        return redirect(url_for('livestock.list_livestock'))


@livestock_bp.route('/create/<int:farm_id>', methods=['GET', 'POST'])
@login_required
def create_livestock(farm_id):
    """Create new livestock record"""
    try:
        farm = Farm.query.get_or_404(farm_id)
        user = User.query.get(session['user_id'])
        
        # Only farmers can create livestock
        if user.role != 'farmer':
            flash('Only farmers can create livestock records', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        # Check farm ownership
        if farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        if request.method == 'POST':
            # Parse acquisition_date with error handling
            acquisition_date = None
            try:
                date_str = request.form.get('acquisition_date')
                if date_str:
                    acquisition_date = datetime.strptime(date_str, '%Y-%m-%d')
                else:
                    acquisition_date = datetime.utcnow()
            except (ValueError, TypeError):
                acquisition_date = datetime.utcnow()
            
            livestock = Livestock(
                farm_id=farm_id,
                animal_type=request.form.get('animal_type'),
                breed=request.form.get('breed'),
                unique_id=request.form.get('unique_id'),
                age_months=int(request.form.get('age_months', 0)) if request.form.get('age_months') else None,
                gender=request.form.get('gender'),
                weight_kg=float(request.form.get('weight_kg', 0)) if request.form.get('weight_kg') else None,
                count=int(request.form.get('count', 1)),
                location_description=request.form.get('location_description'),
                acquisition_date=acquisition_date,
                acquisition_cost=float(request.form.get('acquisition_cost', 0)) if request.form.get('acquisition_cost') else None,
                source=request.form.get('source'),
                notes=request.form.get('notes')
            )
            
            db.session.add(livestock)
            db.session.commit()
            
            flash(f'Successfully created {livestock.animal_type} record', 'success')
            return redirect(url_for('livestock.view_livestock', livestock_id=livestock.id))
        
        return render_template('livestock/create.html',
                             farm=farm,
                             animal_types=ANIMAL_TYPES,
                             user=user)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating livestock: {str(e)}", exc_info=True)
        flash(f'Error creating livestock record: {str(e)}', 'error')
        return redirect(url_for('livestock.list_livestock'))


@livestock_bp.route('/<int:livestock_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_livestock(livestock_id):
    """Edit livestock record"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        # Only farmers can edit livestock
        if user.role != 'farmer':
            flash('Only farmers can edit livestock', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        # Check farm ownership
        if livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        if request.method == 'POST':
            livestock.animal_type = request.form.get('animal_type')
            livestock.breed = request.form.get('breed')
            livestock.age_months = int(request.form.get('age_months', 0)) if request.form.get('age_months') else None
            livestock.gender = request.form.get('gender')
            livestock.weight_kg = float(request.form.get('weight_kg', 0)) if request.form.get('weight_kg') else None
            livestock.count = int(request.form.get('count', 1))
            livestock.location_description = request.form.get('location_description')
            livestock.status = request.form.get('status')
            livestock.notes = request.form.get('notes')
            livestock.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Livestock record updated successfully', 'success')
            return redirect(url_for('livestock.view_livestock', livestock_id=livestock.id))
        
        return render_template('livestock/edit.html',
                             livestock=livestock,
                             animal_types=ANIMAL_TYPES,
                             user=user)
    except Exception as e:
        logger.error(f"Error editing livestock: {str(e)}")
        flash('Error updating livestock record', 'error')
        return redirect(url_for('livestock.list_livestock'))


@livestock_bp.route('/<int:livestock_id>/delete', methods=['POST'])
@login_required
def delete_livestock(livestock_id):
    """Delete livestock record"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        farm_id = livestock.farm_id
        
        # Only farmers can delete livestock
        if user.role != 'farmer':
            flash('Only farmers can delete livestock', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        # Check farm ownership
        if livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        db.session.delete(livestock)
        db.session.commit()
        
        flash('Livestock record deleted successfully', 'success')
        return redirect(url_for('livestock.list_livestock', farm_id=farm_id))
    except Exception as e:
        logger.error(f"Error deleting livestock: {str(e)}")
        flash('Error deleting livestock record', 'error')
        return redirect(url_for('livestock.list_livestock'))


# Health Records Routes

@livestock_bp.route('/<int:livestock_id>/health/add', methods=['POST'])
@login_required
def add_health_record(livestock_id):
    """Add health record with automatic vaccine inventory deduction"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
        
        record_type = request.form.get('record_type')
        vaccine_inventory_id = request.form.get('vaccine_inventory_id') if record_type == 'vaccine' else None
        vaccine_inventory = None
        
        # If vaccine record, handle inventory deduction
        if record_type == 'vaccine' and vaccine_inventory_id:
            vaccine_inventory = VaccineInventory.query.get_or_404(int(vaccine_inventory_id))
            
            # Check if enough vaccine available
            if vaccine_inventory.quantity_remaining <= 0:
                flash(f'No {vaccine_inventory.vaccine_name} available in inventory', 'error')
                return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
            
            # Auto-populate name, dosage, and cost from vaccine inventory
            name = vaccine_inventory.vaccine_name
            dosage = f"1 {vaccine_inventory.unit_type}"
            cost = vaccine_inventory.cost_per_unit
            
            # Deduct from inventory
            vaccine_inventory.quantity_used += 1
            logger.info(f"Vaccine used: {vaccine_inventory.vaccine_name}, Remaining: {vaccine_inventory.quantity_remaining}")
        else:
            name = request.form.get('name')
            dosage = request.form.get('dosage')
            cost = float(request.form.get('cost', 0)) if request.form.get('cost') else None
        
        health_record = HealthRecord(
            livestock_id=livestock_id,
            vaccine_inventory_id=vaccine_inventory_id,
            record_type=record_type,
            name=name,
            description=request.form.get('description'),
            dosage=dosage,
            date_administered=datetime.strptime(request.form.get('date_administered'), '%Y-%m-%d'),
            next_due_date=datetime.strptime(request.form.get('next_due_date'), '%Y-%m-%d') if request.form.get('next_due_date') else None,
            veterinarian_name=request.form.get('veterinarian_name'),
            clinic_name=request.form.get('clinic_name'),
            contact_info=request.form.get('contact_info'),
            cost=cost,
            result=request.form.get('result'),
            notes=request.form.get('notes')
        )
        
        db.session.add(health_record)
        if vaccine_inventory:
            db.session.add(vaccine_inventory)
        db.session.commit()
        
        flash('Health record added successfully', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding health record: {str(e)}")
        flash('Error adding health record', 'error')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


@livestock_bp.route('/health/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_health_record(record_id):
    """Delete health record"""
    try:
        health_record = HealthRecord.query.get_or_404(record_id)
        user = User.query.get(session['user_id'])
        livestock_id = health_record.livestock_id
        
        # Check permissions
        if user.role == 'farmer' and health_record.livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        db.session.delete(health_record)
        db.session.commit()
        
        flash('Health record deleted', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        logger.error(f"Error deleting health record: {str(e)}")
        flash('Error deleting health record', 'error')
        return redirect(url_for('livestock.list_livestock'))


# Nutrition Records Routes

@livestock_bp.route('/<int:livestock_id>/nutrition/add', methods=['POST'])
@login_required
def add_nutrition_record(livestock_id):
    """Add nutrition record"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
        
        nutrition_record = NutritionRecord(
            livestock_id=livestock_id,
            food_type=request.form.get('food_type'),
            description=request.form.get('description'),
            quantity_kg=float(request.form.get('quantity_kg', 0)),
            quantity_unit=request.form.get('quantity_unit', 'kg'),
            feeding_frequency=request.form.get('feeding_frequency'),
            feeding_time=request.form.get('feeding_time'),
            cost_per_unit=float(request.form.get('cost_per_unit', 0)) if request.form.get('cost_per_unit') else None,
            supplier_name=request.form.get('supplier_name'),
            supplier_contact=request.form.get('supplier_contact'),
            notes=request.form.get('notes'),
            is_active=request.form.get('is_active') == 'on'
        )
        
        db.session.add(nutrition_record)
        db.session.commit()
        
        flash('Nutrition record added successfully', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        logger.error(f"Error adding nutrition record: {str(e)}")
        flash('Error adding nutrition record', 'error')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


@livestock_bp.route('/nutrition/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_nutrition_record(record_id):
    """Delete nutrition record"""
    try:
        nutrition_record = NutritionRecord.query.get_or_404(record_id)
        user = User.query.get(session['user_id'])
        livestock_id = nutrition_record.livestock_id
        
        if user.role == 'farmer' and nutrition_record.livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        db.session.delete(nutrition_record)
        db.session.commit()
        
        flash('Nutrition record deleted', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        logger.error(f"Error deleting nutrition record: {str(e)}")
        flash('Error deleting nutrition record', 'error')
        return redirect(url_for('livestock.list_livestock'))


# Productivity Records Routes

@livestock_bp.route('/<int:livestock_id>/productivity/add', methods=['POST'])
@login_required
def add_productivity_record(livestock_id):
    """Add productivity record"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
        
        productivity_record = ProductivityRecord(
            livestock_id=livestock_id,
            metric_type=request.form.get('metric_type'),
            quantity=float(request.form.get('quantity', 0)),
            unit=request.form.get('unit'),
            record_date=datetime.strptime(request.form.get('record_date'), '%Y-%m-%d'),
            market_value=float(request.form.get('market_value', 0)) if request.form.get('market_value') else None,
            notes=request.form.get('notes')
        )
        
        db.session.add(productivity_record)
        db.session.commit()
        
        flash('Productivity record added successfully', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        logger.error(f"Error adding productivity record: {str(e)}")
        flash('Error adding productivity record', 'error')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


@livestock_bp.route('/productivity/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_productivity_record(record_id):
    """Delete productivity record"""
    try:
        productivity_record = ProductivityRecord.query.get_or_404(record_id)
        user = User.query.get(session['user_id'])
        livestock_id = productivity_record.livestock_id
        
        if user.role == 'farmer' and productivity_record.livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        db.session.delete(productivity_record)
        db.session.commit()
        
        flash('Productivity record deleted', 'success')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))
    except Exception as e:
        logger.error(f"Error deleting productivity record: {str(e)}")
        flash('Error deleting productivity record', 'error')
        return redirect(url_for('livestock.list_livestock'))


# ── Death Event ───────────────────────────────────────────────────────────────

@livestock_bp.route('/<int:livestock_id>/record-death', methods=['POST'])
@login_required
def record_death(livestock_id):
    """Record animal death(s)"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])

        if user.role != 'farmer' or livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))

        count_died = int(request.form.get('count_died', 1))
        count_died = max(1, min(count_died, livestock.count))

        event_date_str = request.form.get('event_date')
        event_date = datetime.strptime(event_date_str, '%Y-%m-%d') if event_date_str else datetime.utcnow()

        event = LivestockEvent(
            livestock_id=livestock_id,
            event_type='death',
            event_date=event_date,
            count_affected=count_died,
            cause_of_death=request.form.get('cause_of_death'),
            notes=request.form.get('notes')
        )
        db.session.add(event)

        # Update count / status
        livestock.count -= count_died
        if livestock.count <= 0:
            livestock.count = 0
            livestock.status = 'deceased'
            livestock.status_date = event_date

        db.session.commit()
        flash(f'Recorded {count_died} death(s). Remaining: {livestock.count}', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording death: {str(e)}", exc_info=True)
        flash('Error recording death event', 'error')

    return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


# ── Sale Event ────────────────────────────────────────────────────────────────

@livestock_bp.route('/<int:livestock_id>/record-sale', methods=['POST'])
@login_required
def record_sale(livestock_id):
    """Record animal sale(s)"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])

        if user.role != 'farmer' or livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))

        count_sold = int(request.form.get('count_sold', 1))
        count_sold = max(1, min(count_sold, livestock.count))

        price_per_head = float(request.form.get('price_per_head', 0)) if request.form.get('price_per_head') else None
        total_revenue = (price_per_head * count_sold) if price_per_head else None

        event_date_str = request.form.get('event_date')
        event_date = datetime.strptime(event_date_str, '%Y-%m-%d') if event_date_str else datetime.utcnow()

        event = LivestockEvent(
            livestock_id=livestock_id,
            event_type='sale',
            event_date=event_date,
            count_affected=count_sold,
            buyer_name=request.form.get('buyer_name'),
            buyer_contact=request.form.get('buyer_contact'),
            price_per_head=price_per_head,
            total_revenue=total_revenue,
            notes=request.form.get('notes')
        )
        db.session.add(event)

        livestock.count -= count_sold
        if livestock.count <= 0:
            livestock.count = 0
            livestock.status = 'sold'
            livestock.status_date = event_date

        db.session.commit()
        rev_str = f' | Revenue: ₱{total_revenue:,.2f}' if total_revenue else ''
        flash(f'Sale recorded: {count_sold} head{rev_str}. Remaining: {livestock.count}', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording sale: {str(e)}", exc_info=True)
        flash('Error recording sale event', 'error')

    return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


# ── Weight Log ────────────────────────────────────────────────────────────────

@livestock_bp.route('/<int:livestock_id>/log-weight', methods=['POST'])
@login_required
def log_weight(livestock_id):
    """Log a weight snapshot"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])

        if user.role != 'farmer' or livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))

        weight_kg = float(request.form.get('weight_kg'))
        weighed_at_str = request.form.get('weighed_at')
        weighed_at = datetime.strptime(weighed_at_str, '%Y-%m-%d') if weighed_at_str else datetime.utcnow()

        log = LivestockWeightLog(
            livestock_id=livestock_id,
            weight_kg=weight_kg,
            weighed_at=weighed_at,
            notes=request.form.get('notes')
        )
        db.session.add(log)

        # Update the current weight on the livestock record
        livestock.weight_kg = weight_kg
        livestock.updated_at = datetime.utcnow()

        db.session.commit()
        flash(f'Weight logged: {weight_kg} kg', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error logging weight: {str(e)}", exc_info=True)
        flash('Error logging weight', 'error')

    return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))


# ── Printable Record Card ─────────────────────────────────────────────────────

@livestock_bp.route('/<int:livestock_id>/record-card', methods=['GET'])
@login_required
def record_card(livestock_id):
    """Printable animal record card for buyers"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])

        # Any authenticated user may view the card (farmer, officer, admin)
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))

        health = HealthRecord.query.filter_by(livestock_id=livestock_id).order_by(HealthRecord.date_administered.desc()).all()
        weight_logs = LivestockWeightLog.query.filter_by(livestock_id=livestock_id).order_by(LivestockWeightLog.weighed_at.desc()).all()
        events = LivestockEvent.query.filter_by(livestock_id=livestock_id).order_by(LivestockEvent.event_date.desc()).all()

        return render_template('livestock/record_card.html',
                               livestock=livestock,
                               health=health,
                               weight_logs=weight_logs,
                               events=events,
                               user=user,
                               now=datetime.utcnow())
    except Exception as e:
        logger.error(f"Error loading record card: {str(e)}", exc_info=True)
        flash('Error loading record card', 'error')
        return redirect(url_for('livestock.view_livestock', livestock_id=livestock_id))

