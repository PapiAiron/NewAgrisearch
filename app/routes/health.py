"""
Phase 4 - Health Management Routes
Enhanced vaccine, disease, and health tracking endpoints
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app import db
from app.models.user import User
from app.models.farm import Farm
from app.models.livestock import Livestock, HealthRecord
from app.models.health import VaccineInventory, DiseaseRecord, HealthAlert
from app.models.distribution import DistributionRecord
from functools import wraps
from datetime import datetime, timedelta
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

health_bp = Blueprint('health', __name__, url_prefix='/health')


def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ============= VACCINE INVENTORY ROUTES =============

@health_bp.route('/vaccines', methods=['GET'])
@login_required
def list_vaccines():
    """List vaccine inventory with farms and animals"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        # Get user's farms based on role
        if user.role == 'farmer':
            farms = db.session.query(Farm).filter(Farm.owner_id == user.id, Farm.is_active == True).all()
        elif user.role in ['victoria_admin', 'system_admin']:
            # Admins see all farms
            farms = db.session.query(Farm).filter(Farm.is_active == True).all()
        else:
            farms = []
        
        farm_ids = [f.id for f in farms]
        
        # Get filters
        farm_id = request.args.get('farm_id', type=int)
        
        # Build vaccine query - show ALL vaccines (active or not) for inventory view
        if farm_ids:
            vaccine_query = VaccineInventory.query.filter(VaccineInventory.farm_id.in_(farm_ids))
        else:
            vaccine_query = VaccineInventory.query.filter(False)
        
        # Filter by specific farm if selected
        if farm_id and farm_id in farm_ids:
            vaccine_query = vaccine_query.filter(VaccineInventory.farm_id == farm_id)
        
        vaccines = vaccine_query.order_by(VaccineInventory.expiry_date).all()
        
        # Calculate statistics
        total_vaccines = len(vaccines)
        expired_count = len([v for v in vaccines if v.is_expired])
        expiring_soon = len([v for v in vaccines if v.expiry_status == 'expiring_soon'])
        total_value = sum([v.total_cost or 0 for v in vaccines])
        
        # Group vaccines by farm
        vaccines_by_farm = {}
        for vaccine in vaccines:
            farm_obj = vaccine.farm
            if farm_obj:
                if farm_obj.id not in vaccines_by_farm:
                    vaccines_by_farm[farm_obj.id] = {
                        'farm': farm_obj,
                        'vaccines': []
                    }
                vaccines_by_farm[farm_obj.id]['vaccines'].append(vaccine)
        
        # Build comprehensive farm data with animals and vaccination status
        farms_data = []
        for farm in farms:
            # Get all livestock for this farm
            livestock = Livestock.query.filter(Livestock.farm_id == farm.id, Livestock.status == 'active').all()
            
            # Build livestock data with vaccination info
            livestock_data = []
            for animal in livestock:
                # Get recent vaccine records for this animal
                recent_vaccines = HealthRecord.query.filter(
                    HealthRecord.livestock_id == animal.id,
                    HealthRecord.record_type == 'vaccine'
                ).order_by(HealthRecord.date_administered.desc()).limit(5).all()
                
                # Get upcoming vaccines
                upcoming = HealthRecord.query.filter(
                    HealthRecord.livestock_id == animal.id,
                    HealthRecord.record_type == 'vaccine',
                    HealthRecord.next_due_date != None,
                    HealthRecord.next_due_date > datetime.utcnow()
                ).order_by(HealthRecord.next_due_date).all()
                
                livestock_data.append({
                    'animal': animal,
                    'recent_vaccines': recent_vaccines,
                    'upcoming_vaccines': upcoming
                })
            
            # Get available vaccines for this farm
            farm_vaccines = vaccines_by_farm.get(farm.id, {}).get('vaccines', [])
            available_vaccines = [v for v in farm_vaccines if v.quantity_remaining > 0 and not v.is_expired]
            
            farms_data.append({
                'farm': farm,
                'livestock': livestock_data,
                'available_vaccines': available_vaccines,
                'all_vaccines': farm_vaccines,
                'vaccine_count': len(farm_vaccines)
            })
        
        logger.info(f"[VACCINE_INVENTORY] Loaded vaccine inventory for user {user.username}")
        return render_template('health/vaccines.html',
                             vaccines=vaccines,
                             vaccines_by_farm=vaccines_by_farm,
                             farms=farms,
                             farms_data=farms_data,
                             total_vaccines=total_vaccines,
                             expired_count=expired_count,
                             expiring_soon=expiring_soon,
                             total_value=total_value,
                             user=user)
    except Exception as e:
        logger.error(f"Error listing vaccines: {str(e)}", exc_info=True)
        flash(f'Error loading vaccine inventory: {str(e)}', 'error')
        return redirect(url_for('dashboard.index'))


@health_bp.route('/vaccines/add/<int:farm_id>', methods=['GET', 'POST'])
@login_required
def add_vaccine(farm_id):
    """Add vaccine to inventory"""
    try:
        farm = Farm.query.get_or_404(farm_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        if user.role == 'farmer' and farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('health.list_vaccines'))
        
        if request.method == 'POST':
            vaccine = VaccineInventory(
                farm_id=farm_id,
                vaccine_name=request.form.get('vaccine_name'),
                vaccine_code=request.form.get('vaccine_code'),
                description=request.form.get('description'),
                quantity_units=int(request.form.get('quantity_units', 0)),
                unit_type=request.form.get('unit_type', 'dose'),
                storage_location=request.form.get('storage_location'),
                storage_temperature=request.form.get('storage_temperature'),
                purchase_date=datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d'),
                expiry_date=datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d'),
                cost_per_unit=float(request.form.get('cost_per_unit', 0)) if request.form.get('cost_per_unit') else None,
                total_cost=float(request.form.get('total_cost', 0)) if request.form.get('total_cost') else None,
                supplier_name=request.form.get('supplier_name'),
                supplier_contact=request.form.get('supplier_contact'),
                notes=request.form.get('notes')
            )
            
            db.session.add(vaccine)
            db.session.commit()
            
            flash(f'Successfully added {vaccine.vaccine_name} to inventory', 'success')
            return redirect(url_for('health.list_vaccines', farm_id=farm_id))
        
        return render_template('health/add_vaccine.html', farm=farm, user=user)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding vaccine: {str(e)}", exc_info=True)
        flash(f'Error adding vaccine: {str(e)}', 'error')
        return redirect(url_for('health.list_vaccines'))


# ============= DISEASE RECORDS ROUTES =============

@health_bp.route('/diseases/<int:livestock_id>', methods=['GET'])
@login_required
def list_diseases(livestock_id):
    """List disease records for an animal"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        diseases = DiseaseRecord.query.filter_by(livestock_id=livestock_id).order_by(DiseaseRecord.onset_date.desc()).all()
        
        # Calculate statistics
        total_diseases = len(diseases)
        active_diseases = len([d for d in diseases if d.outcome == 'ongoing'])
        total_treatment_cost = sum([d.treatment_cost + (d.medication_cost or 0) for d in diseases])
        
        logger.info(f"[DISEASE_RECORDS] Loaded disease records for livestock {livestock.unique_id}")
        return render_template('health/diseases.html',
                             livestock=livestock,
                             diseases=diseases,
                             total_diseases=total_diseases,
                             active_diseases=active_diseases,
                             total_treatment_cost=total_treatment_cost,
                             user=user)
    except Exception as e:
        logger.error(f"Error listing diseases: {str(e)}", exc_info=True)
        flash(f'Error loading disease records: {str(e)}', 'error')
        return redirect(url_for('livestock.list_livestock'))


@health_bp.route('/diseases/add/<int:livestock_id>', methods=['GET', 'POST'])
@login_required
def add_disease(livestock_id):
    """Add disease record"""
    try:
        livestock = Livestock.query.get_or_404(livestock_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('livestock.list_livestock'))
        
        if request.method == 'POST':
            onset_date = datetime.strptime(request.form.get('onset_date'), '%Y-%m-%d')
            
            disease = DiseaseRecord(
                livestock_id=livestock_id,
                disease_name=request.form.get('disease_name'),
                disease_code=request.form.get('disease_code'),
                description=request.form.get('description'),
                severity=request.form.get('severity'),
                onset_date=onset_date,
                diagnosis_date=datetime.strptime(request.form.get('diagnosis_date'), '%Y-%m-%d') if request.form.get('diagnosis_date') else None,
                treatment_start_date=datetime.strptime(request.form.get('treatment_start_date'), '%Y-%m-%d') if request.form.get('treatment_start_date') else None,
                symptoms=request.form.get('symptoms'),
                diagnosis_method=request.form.get('diagnosis_method'),
                treatment_given=request.form.get('treatment_given'),
                medications_used=request.form.get('medications_used'),
                veterinarian_name=request.form.get('veterinarian_name'),
                clinic_name=request.form.get('clinic_name'),
                outcome=request.form.get('outcome', 'ongoing'),
                treatment_cost=float(request.form.get('treatment_cost', 0)) if request.form.get('treatment_cost') else None,
                medication_cost=float(request.form.get('medication_cost', 0)) if request.form.get('medication_cost') else None,
                notes=request.form.get('notes')
            )
            
            db.session.add(disease)
            db.session.commit()
            
            flash(f'Disease record for {livestock.unique_id} added successfully', 'success')
            return redirect(url_for('health.list_diseases', livestock_id=livestock_id))
        
        return render_template('health/add_disease.html', livestock=livestock, user=user)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding disease: {str(e)}", exc_info=True)
        flash(f'Error adding disease record: {str(e)}', 'error')
        return redirect(url_for('livestock.list_livestock'))


# ============= HEALTH ALERTS ROUTES =============

@health_bp.route('/alerts', methods=['GET'])
@login_required
def list_alerts():
    """List health alerts"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        # Get user's farms
        if user.role == 'farmer':
            farms = db.session.query(Farm).filter(Farm.owner_id == user.id).all()
        else:
            farms = Farm.query.all()
        
        farm_ids = [f.id for f in farms]
        
        # Get livestock for user's farms
        livestock_ids = db.session.query(Livestock.id).filter(Livestock.farm_id.in_(farm_ids)).all()
        livestock_ids = [l[0] for l in livestock_ids]
        
        # Get filters
        status_filter = request.args.get('status', '')  # resolved, pending
        priority_filter = request.args.get('priority', '')  # low, medium, high, critical
        
        # Build query
        query = HealthAlert.query.filter(HealthAlert.livestock_id.in_(livestock_ids)) if livestock_ids else HealthAlert.query.filter(False)
        
        if status_filter == 'resolved':
            query = query.filter(HealthAlert.is_resolved == True)
        elif status_filter == 'pending':
            query = query.filter(HealthAlert.is_resolved == False)
        
        if priority_filter:
            query = query.filter(HealthAlert.priority == priority_filter)
        
        alerts = query.order_by(HealthAlert.alert_date.desc()).all()
        
        # Calculate statistics
        total_alerts = len(alerts)
        pending_alerts = len([a for a in alerts if not a.is_resolved])
        critical_alerts = len([a for a in alerts if a.priority == 'critical' and not a.is_resolved])
        overdue_alerts = len([a for a in alerts if a.is_overdue])
        
        logger.info(f"[HEALTH_ALERTS] Loaded health alerts for user {user.username}")
        return render_template('health/alerts.html',
                             alerts=alerts,
                             total_alerts=total_alerts,
                             pending_alerts=pending_alerts,
                             critical_alerts=critical_alerts,
                             overdue_alerts=overdue_alerts,
                             user=user)
    except Exception as e:
        logger.error(f"Error listing alerts: {str(e)}", exc_info=True)
        flash(f'Error loading health alerts: {str(e)}', 'error')
        return redirect(url_for('dashboard.index'))


@health_bp.route('/alerts/resolve/<int:alert_id>', methods=['POST'])
@login_required
def resolve_alert(alert_id):
    """Resolve a health alert"""
    try:
        alert = HealthAlert.query.get_or_404(alert_id)
        user = User.query.get(session['user_id'])
        
        # Check permissions
        livestock = alert.livestock
        if user.role == 'farmer' and livestock.farm.owner_id != user.id:
            flash('Access denied', 'error')
            return redirect(url_for('health.list_alerts'))
        
        alert.is_resolved = True
        alert.resolved_date = datetime.utcnow()
        alert.resolution_notes = request.form.get('resolution_notes', '')
        
        db.session.commit()
        
        flash('Alert resolved successfully', 'success')
        return redirect(url_for('health.list_alerts'))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resolving alert: {str(e)}", exc_info=True)
        flash(f'Error resolving alert: {str(e)}', 'error')
        return redirect(url_for('health.list_alerts'))


# ============= VACCINATION ENDPOINTS =============

@health_bp.route('/api/vaccinate', methods=['POST'])
@login_required
def vaccinate_animal():
    """API endpoint to vaccinate an animal from inventory (farm vaccine or distributed supply)"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 401
        
        data = request.get_json()
        livestock_id = data.get('livestock_id')
        vaccine_id = data.get('vaccine_inventory_id')  # Format: 'farm_{id}' or 'dist_{id}'
        notes = data.get('notes', '')
        
        if not livestock_id or not vaccine_id:
            return jsonify({'success': False, 'message': 'Missing livestock or vaccine ID'}), 400
        
        # Get the livestock
        livestock = Livestock.query.get(livestock_id)
        if not livestock:
            return jsonify({'success': False, 'message': 'Animal not found'}), 404
        
        # Use the group count so inventory is deducted per head
        animal_count = max(1, livestock.count or 1)
        
        # Check user has access to this livestock's farm
        farm = livestock.farm
        if user.role == 'farmer' and farm.owner_id != user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Determine vaccine source and get vaccine details
        vaccine_name = None
        vaccine_code = None
        dosage = None
        cost = None
        
        if vaccine_id.startswith('farm_'):
            # Farm-specific vaccine inventory
            actual_id = int(vaccine_id.split('_')[1])
            vaccine = VaccineInventory.query.get(actual_id)
            
            if not vaccine:
                return jsonify({'success': False, 'message': 'Vaccine not found'}), 404
            
            if vaccine.farm_id != farm.id:
                return jsonify({'success': False, 'message': 'Vaccine does not belong to this farm'}), 400
            
            if vaccine.is_expired:
                return jsonify({'success': False, 'message': 'Vaccine has expired'}), 400
            
            if vaccine.quantity_remaining < animal_count:
                return jsonify({'success': False, 'message': f'Not enough vaccine stock. Need {animal_count} dose(s) but only {vaccine.quantity_remaining} available.'}), 400
            
            vaccine_name = vaccine.vaccine_name
            vaccine_code = vaccine.vaccine_code
            dosage = f"{animal_count} {vaccine.unit_type} ({animal_count} head)"
            cost = (vaccine.cost_per_unit or 0) * animal_count
            
            # Create health record for the vaccination
            health_record = HealthRecord(
                livestock_id=livestock_id,
                record_type='vaccine',
                name=vaccine_name,
                description=vaccine_code,
                dosage=dosage,
                cost=cost,
                date_administered=datetime.utcnow(),
                veterinarian_name=user.full_name,
                vaccine_inventory_id=actual_id,  # Link to farm vaccine
                notes=notes
            )
            
            # Deduct one dose per head in the group
            vaccine.quantity_used += animal_count
            
        elif vaccine_id.startswith('dist_'):
            # Distributed supply vaccine
            actual_id = int(vaccine_id.split('_')[1])
            dist_record = DistributionRecord.query.get(actual_id)
            
            if not dist_record:
                return jsonify({'success': False, 'message': 'Distribution record not found'}), 404
            
            if dist_record.status != 'verified':
                return jsonify({'success': False, 'message': 'Vaccine distribution not verified'}), 400
            
            if dist_record.quantity_distributed < animal_count:
                return jsonify({'success': False, 'message': f'Not enough vaccine stock. Need {animal_count} dose(s) but only {dist_record.quantity_distributed} available.'}), 400
            
            vaccine_name = dist_record.request.supply_name
            vaccine_code = dist_record.request.supply_name
            dosage = f"{animal_count} {dist_record.request.unit} ({animal_count} head)"
            cost = 0  # Distributed supplies may not have cost tracking
            
            # Create health record for the vaccination
            health_record = HealthRecord(
                livestock_id=livestock_id,
                record_type='vaccine',
                name=vaccine_name,
                description=vaccine_code,
                dosage=dosage,
                cost=cost,
                date_administered=datetime.utcnow(),
                veterinarian_name=user.full_name,
                vaccine_inventory_id=None,  # No FK to farm inventory for distributed vaccines
                notes=notes
            )
            
            # Deduct one dose per head in the group
            dist_record.quantity_distributed = max(0, dist_record.quantity_distributed - animal_count)
        else:
            return jsonify({'success': False, 'message': 'Invalid vaccine source'}), 400
        
        # Add to session and commit
        db.session.add(health_record)
        db.session.commit()
        
        logger.info(f"[VACCINATION] Vaccinated livestock {livestock.unique_id} with {vaccine_name} x{animal_count} - User: {user.full_name}")
        
        return jsonify({
            'success': True,
            'message': f'Vaccinated {animal_count} head(s) with {vaccine_name}. {animal_count} dose(s) deducted from inventory.',
            'health_record_id': health_record.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error vaccinating animal: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
