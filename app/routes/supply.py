from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from app import db
from app.models.supply import Supply, SupplyInventory, SupplyDistribution, SupplyUsageRecord, FarmSupplyInventory, FarmSupplyUsage
from app.models.farm import Farm
from app.models.user import User
from app.models.distribution import DistributionRequest
from datetime import datetime, date
from functools import wraps
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

supply_bp = Blueprint('supply', __name__, url_prefix='/supply')

def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    """Decorator to check if user is staff/officer"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if user.role not in ['victoria_admin', 'system_admin']:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

# ===== SUPPLY INVENTORY ROUTES =====

@supply_bp.route('/inventory', methods=['GET'])
@login_required
def inventory_view():
    """View supply inventory with stock levels"""
    user = User.query.get(session['user_id'])
    
    # Staff can see all supplies; farmers see only their farm's inventory
    if user.role == 'farmer':
        # Get farmer's farms
        farms = Farm.query.filter_by(owner_id=user.id).all()
        if not farms:
            flash('You have no farms', 'info')
            return redirect(url_for('dashboard.index'))
        
        farm_ids = [farm.id for farm in farms]
        
        # Get distribution records that were verified (received)
        from app.models.distribution import DistributionRecord
        
        municipality_supplies = []
        # Get verified distribution records
        try:
            records = DistributionRecord.query.filter(
                DistributionRecord.request_id.in_(
                    db.session.query(DistributionRequest.id).filter(
                        DistributionRequest.farm_id.in_(farm_ids)
                    )
                ),
                DistributionRecord.status == 'verified'
            ).all()
            
            for record in records:
                # Ensure all required attributes exist
                if not hasattr(record, 'request') or not record.request:
                    continue
                if not hasattr(record, 'quantity_distributed'):
                    continue
                    
                municipality_supplies.append({
                    'item_name': record.request.supply_name,
                    'quantity': record.quantity_distributed,
                    'unit': record.request.unit,
                    'source': 'municipality',
                    'date_acquired': record.verified_at,
                    'status': record.status,
                    'type': record.request.supply_type
                })
        except Exception as e:
            logger.error(f"Error loading municipality supplies: {str(e)}")
            municipality_supplies = []
        
        # Get farmer-owned supplies (purchased or received)
        try:
            farmer_supplies = FarmSupplyInventory.query.filter(
                FarmSupplyInventory.farm_id.in_(farm_ids)
            ).all()
        except Exception as e:
            logger.error(f"Error loading farmer supplies: {str(e)}")
            farmer_supplies = []
        
        # Get usage history
        try:
            usage_history = FarmSupplyUsage.query.join(
                FarmSupplyInventory, FarmSupplyUsage.farm_supply_id == FarmSupplyInventory.id
            ).filter(
                FarmSupplyInventory.farm_id.in_(farm_ids)
            ).order_by(FarmSupplyUsage.usage_date.desc()).all()
        except Exception as e:
            logger.error(f"Error loading usage history: {str(e)}")
            usage_history = []

        # Build name lookup for related livestock/crops so the history shows real names
        related_names = {}
        try:
            from app.models.livestock import Livestock
            from app.models.crop import Crop
            for u in usage_history:
                key = f"{u.related_model}_{u.related_id}"
                if key in related_names or not u.related_model or not u.related_id:
                    continue
                if u.related_model == 'livestock':
                    animal = Livestock.query.get(u.related_id)
                    if animal:
                        label = animal.unique_id or f"#{animal.id}"
                        related_names[key] = f"{animal.animal_type.title()} – {label}"
                    else:
                        related_names[key] = f"Livestock #{u.related_id}"
                elif u.related_model == 'crop':
                    crop = Crop.query.get(u.related_id)
                    related_names[key] = f"{crop.crop_type} (Field {crop.id})" if crop else f"Crop #{u.related_id}"
                elif u.related_model == 'farm':
                    related_names[key] = "General Farm Use"
                elif u.related_model == 'storage':
                    related_names[key] = "Storage / Preservation"
        except Exception as e:
            logger.error(f"Error building related names: {str(e)}")

        return render_template('supply/farmer_inventory.html', 
                             municipality_supplies=municipality_supplies,
                             farmer_supplies=farmer_supplies,
                             usage_history=usage_history,
                             related_names=related_names,
                             farms=farms,
                             user=user)
    else:
        # Staff can see all supplies
        if user.role not in ['victoria_admin', 'system_admin']:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard.index'))
        
        supplies = Supply.query.all()
        supply_data = []
        
        for supply in supplies:
            inventory_locations = SupplyInventory.query.filter_by(supply_id=supply.id).all()
            total_available = sum(inv.quantity_available for inv in inventory_locations)
            total_reserved = sum(inv.quantity_reserved for inv in inventory_locations)
            is_low = supply.is_low_stock()
            
            supply_data.append({
                'supply': supply,
                'total_available': total_available,
                'total_reserved': total_reserved,
                'available_for_dist': total_available - total_reserved,
                'is_low': is_low,
                'inventory_locations': inventory_locations
            })
        
        return render_template('supply/inventory.html', supply_data=supply_data, user=user)

@supply_bp.route('/add-supply', methods=['GET', 'POST'])
@login_required
@staff_required
def add_supply():
    """Add a new supply item to the system"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            supply_type = request.form.get('supply_type')
            name = request.form.get('name')
            description = request.form.get('description')
            unit = request.form.get('unit')
            unit_cost = request.form.get('unit_cost')
            reorder_level = request.form.get('reorder_level', 10)
            
            supply = Supply(
                supply_type=supply_type,
                name=name,
                description=description,
                unit=unit,
                unit_cost=float(unit_cost) if unit_cost else None,
                reorder_level=float(reorder_level)
            )
            
            db.session.add(supply)
            db.session.commit()
            
            flash(f'Supply "{name}" added successfully', 'success')
            return redirect(url_for('supply.inventory_view'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding supply: {str(e)}', 'error')
    
    supply_types = ['vaccine', 'feed', 'fertilizer', 'seeds']
    units = ['doses', 'kg', 'bottles', 'packets', 'liters', 'bags']
    
    return render_template('supply/add.html', supply_types=supply_types, units=units, user=user)

@supply_bp.route('/<int:supply_id>/update-stock', methods=['POST'])
@login_required
@staff_required
def update_stock(supply_id):
    """Update supply stock quantity"""
    supply = Supply.query.get_or_404(supply_id)
    
    try:
        inventory_id = request.form.get('inventory_id', type=int)
        new_quantity = request.form.get('quantity', type=float)
        warehouse_location = request.form.get('warehouse_location')
        
        # Get or create inventory location
        if inventory_id:
            inventory = SupplyInventory.query.get_or_404(inventory_id)
        else:
            inventory = SupplyInventory(supply_id=supply_id)
            db.session.add(inventory)
        
        old_quantity = inventory.quantity_available
        inventory.quantity_available = new_quantity
        inventory.warehouse_location = warehouse_location
        inventory.last_updated = datetime.utcnow()
        
        db.session.commit()
        
        quantity_change = new_quantity - old_quantity
        action = 'increased' if quantity_change > 0 else 'decreased'
        
        flash(f'Stock {action} by {abs(quantity_change)} {supply.unit}', 'success')
        return redirect(url_for('supply.inventory_view'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating stock: {str(e)}', 'error')
        return redirect(url_for('supply.inventory_view'))

@supply_bp.route('/<int:supply_id>/distribute', methods=['POST'])
@login_required
@staff_required
def distribute_supply(supply_id):
    """Distribute supply to a farm"""
    supply = Supply.query.get_or_404(supply_id)
    user = User.query.get(session['user_id'])
    
    try:
        farm_id = request.form.get('farm_id', type=int)
        quantity = request.form.get('quantity', type=float)
        notes = request.form.get('notes')
        
        farm = Farm.query.get_or_404(farm_id)
        
        # Check available stock
        total_available = supply.total_available()
        if quantity > total_available:
            flash(f'Not enough stock. Available: {total_available} {supply.unit}', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        # Create distribution record
        distribution = SupplyDistribution(
            supply_id=supply_id,
            farm_id=farm_id,
            distributed_by=user.id,
            quantity=quantity,
            notes=notes,
            status='distributed'
        )
        
        # Deduct from inventory (Phase 1: Simple deduction, Phase 2: More complex logic)
        inventory_locations = SupplyInventory.query.filter_by(supply_id=supply_id).order_by(SupplyInventory.quantity_available.desc()).all()
        remaining_to_deduct = quantity
        
        for inventory in inventory_locations:
            if remaining_to_deduct <= 0:
                break
            
            deduct_amount = min(remaining_to_deduct, inventory.quantity_available)
            inventory.quantity_available -= deduct_amount
            remaining_to_deduct -= deduct_amount
        
        db.session.add(distribution)
        db.session.commit()
        
        flash(f'{quantity} {supply.unit} of {supply.name} distributed to {farm.name}', 'success')
        return redirect(url_for('supply.inventory_view'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error distributing supply: {str(e)}', 'error')
        return redirect(url_for('supply.inventory_view'))

@supply_bp.route('/<int:supply_id>/record-usage', methods=['POST'])
@login_required
def record_usage(supply_id):
    """Record supply usage on a farm"""
    user = User.query.get(session['user_id'])
    supply = Supply.query.get_or_404(supply_id)
    
    try:
        farm_id = request.form.get('farm_id', type=int)
        record_type = request.form.get('record_type')
        quantity_used = request.form.get('quantity_used', type=float)
        related_id = request.form.get('related_id', type=int)
        notes = request.form.get('notes')
        usage_date = request.form.get('usage_date')
        
        farm = Farm.query.get_or_404(farm_id)
        
        # Verify farm ownership for farmers
        if user.role == 'farmer' and farm.owner_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        usage_record = SupplyUsageRecord(
            supply_id=supply_id,
            farm_id=farm_id,
            record_type=record_type,
            related_id=related_id,
            quantity_used=quantity_used,
            usage_date=datetime.strptime(usage_date, '%Y-%m-%d').date() if usage_date else date.today(),
            recorded_by=user.id,
            notes=notes
        )
        
        db.session.add(usage_record)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Usage recorded: {quantity_used} {supply.unit} used'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@supply_bp.route('/distribution-history', methods=['GET'])
@login_required
@staff_required
def distribution_history():
    """View distribution history"""
    user = User.query.get(session['user_id'])
    
    # Filter by date range if provided
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = SupplyDistribution.query
    
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(SupplyDistribution.distribution_date >= start)
    
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(SupplyDistribution.distribution_date <= end)
    
    distributions = query.order_by(SupplyDistribution.distribution_date.desc()).all()
    
    return render_template('supply/distribution_history.html', distributions=distributions, user=user)

@supply_bp.route('/usage-report', methods=['GET'])
@login_required
@staff_required
def usage_report():
    """View supply usage report"""
    user = User.query.get(session['user_id'])
    
    # Filter options
    supply_type = request.args.get('supply_type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = SupplyUsageRecord.query
    
    if supply_type:
        supply_ids = [s.id for s in Supply.query.filter_by(supply_type=supply_type).all()]
        query = query.filter(SupplyUsageRecord.supply_id.in_(supply_ids))
    
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(SupplyUsageRecord.usage_date >= start)
    
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(SupplyUsageRecord.usage_date <= end)
    
    usage_records = query.order_by(SupplyUsageRecord.usage_date.desc()).all()
    supply_types = ['vaccine', 'feed', 'fertilizer', 'seeds']
    
    return render_template('supply/usage_report.html', 
                         usage_records=usage_records, 
                         supply_types=supply_types, 
                         user=user)


# ===== FARM SUPPLY INVENTORY ROUTES (Farmer-Owned Items) =====

@supply_bp.route('/farm-supply/add-item', methods=['POST'])
@login_required
def add_farm_supply_item():
    """Add a new supply item to farmer's inventory"""
    user = User.query.get(session['user_id'])
    
    if user.role != 'farmer':
        flash('Only farmers can manage farm supplies', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        farm_id = request.form.get('farm_id', type=int)
        farm = Farm.query.filter_by(id=farm_id, owner_id=user.id).first()
        
        if not farm:
            flash('Farm not found', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        from app.models.supply import FarmSupplyInventory
        
        item = FarmSupplyInventory(
            farm_id=farm_id,
            item_name=request.form.get('item_name'),
            item_type=request.form.get('item_type'),
            quantity=float(request.form.get('quantity', 0)),
            unit=request.form.get('unit'),
            source=request.form.get('source', 'farmer_purchased'),  # 'municipality' or 'farmer_purchased'
            purchase_date=datetime.strptime(request.form.get('purchase_date', ''), '%Y-%m-%d') if request.form.get('purchase_date') else None,
            unit_cost=float(request.form.get('unit_cost', 0)) if request.form.get('unit_cost') else None,
            notes=request.form.get('notes')
        )
        
        db.session.add(item)
        db.session.commit()
        
        source_label = 'municipality' if item.source == 'municipality' else 'farmer-purchased'
        flash(f'Supply item "{item.item_name}" ({source_label}) added successfully!', 'success')
        return redirect(url_for('supply.inventory_view'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding supply item: {str(e)}', 'error')
        return redirect(url_for('supply.inventory_view'))


@supply_bp.route('/farm-supply/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_farm_supply_item(item_id):
    """Delete a farm supply item"""
    user = User.query.get(session['user_id'])
    
    if user.role != 'farmer':
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        from app.models.supply import FarmSupplyInventory
        
        item = FarmSupplyInventory.query.get(item_id)
        if not item or item.farm.owner_id != user.id:
            flash('Item not found', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        item_name = item.item_name
        db.session.delete(item)
        db.session.commit()
        
        flash(f'Supply item "{item_name}" deleted', 'success')
        return redirect(url_for('supply.inventory_view'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting item: {str(e)}', 'error')
        return redirect(url_for('supply.inventory_view'))


@supply_bp.route('/farm-supply/<int:item_id>/use', methods=['POST'])
@login_required
def use_farm_supply_item(item_id):
    """Record usage of a farm supply item (auto-deducts from inventory)"""
    user = User.query.get(session['user_id'])
    
    if user.role != 'farmer':
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        item = FarmSupplyInventory.query.get(item_id)
        if not item or item.farm.owner_id != user.id:
            flash('Item not found', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        quantity_used = float(request.form.get('quantity_used', 0))
        usage_type = request.form.get('usage_type', 'other')  # livestock_health, crop_application, etc.
        related_model = request.form.get('related_model', '').strip()
        related_id = request.form.get('related_id', type=int)
        notes = request.form.get('notes')
        
        if quantity_used <= 0:
            flash('Quantity must be greater than 0', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        if quantity_used > item.quantity_remaining():
            flash(f'Not enough supply. Available: {item.quantity_remaining()} {item.unit}', 'error')
            return redirect(url_for('supply.inventory_view'))
        
        # ===== VALIDATION: Check related_model and related_id =====
        if related_model and related_model not in ('', 'farm', 'storage'):
            # If related_model is livestock or crop, related_id is required
            if not related_id:
                flash(f'Please select which {related_model} this supply is applied to', 'error')
                return redirect(url_for('supply.inventory_view'))
            
            # Verify the related_id exists and is active
            from app.models.crop import Crop
            from app.models.livestock import Livestock
            
            if related_model == 'crop':
                target = Crop.query.get(related_id)
                if not target:
                    flash('Selected crop not found', 'error')
                    return redirect(url_for('supply.inventory_view'))
                if target.farm_id != item.farm_id:
                    logger.warning(f"User {user.id} attempted to use supply for crop {related_id} not in their farm")
                    flash('Selected crop is not in your farm', 'error')
                    return redirect(url_for('supply.inventory_view'))
                if target.status != 'active':
                    flash(f'Selected crop is not active (status: {target.status}). Only active crops can receive supply usage records.', 'error')
                    return redirect(url_for('supply.inventory_view'))
                    
            elif related_model == 'livestock':
                target = Livestock.query.get(related_id)
                if not target:
                    flash('Selected livestock not found', 'error')
                    return redirect(url_for('supply.inventory_view'))
                if target.farm_id != item.farm_id:
                    logger.warning(f"User {user.id} attempted to use supply for livestock {related_id} not in their farm")
                    flash('Selected livestock is not in your farm', 'error')
                    return redirect(url_for('supply.inventory_view'))
                if target.status != 'active':
                    flash(f'Selected livestock is not active (status: {target.status}). Only active livestock can receive supply usage records.', 'error')
                    return redirect(url_for('supply.inventory_view'))
        
        # Create usage record
        usage = FarmSupplyUsage(
            farm_supply_id=item_id,
            usage_type=usage_type,
            related_model=related_model if related_model else None,
            related_id=related_id if related_model and related_model not in ('', 'farm', 'storage') else None,
            quantity_used=quantity_used,
            usage_date=datetime.strptime(request.form.get('usage_date', ''), '%Y-%m-%d') if request.form.get('usage_date') else date.today(),
            notes=notes,
            recorded_by_id=user.id
        )
        
        db.session.add(usage)
        db.session.commit()
        
        target_text = f" applied to {related_model}" if related_model and related_model not in ('', 'farm', 'storage') else ""
        flash(f'{quantity_used} {item.unit} of "{item.item_name}" marked as used{target_text}', 'success')
        return redirect(url_for('supply.inventory_view'))
    
    except ValueError as ve:
        flash(f'Invalid input: {str(ve)}', 'error')
        logger.error(f"ValueError in use_farm_supply_item: {str(ve)}")
        return redirect(url_for('supply.inventory_view'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error recording usage: {str(e)}', 'error')
        logger.error(f"Error in use_farm_supply_item: {str(e)}", exc_info=True)
        return redirect(url_for('supply.inventory_view'))



@supply_bp.route('/farm-supply/history')
@login_required
def farm_supply_history():
    """View usage history for farm supplies"""
    user = User.query.get(session['user_id'])
    
    if user.role != 'farmer':
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard.index'))
    
    farms = Farm.query.filter_by(owner_id=user.id).all()
    farm_ids = [f.id for f in farms]
    
    usage_history = FarmSupplyUsage.query.join(
        FarmSupplyInventory, FarmSupplyUsage.farm_supply_id == FarmSupplyInventory.id
    ).filter(
        FarmSupplyInventory.farm_id.in_(farm_ids)
    ).order_by(FarmSupplyUsage.usage_date.desc()).all()
    
    return render_template('supply/farm_supply_history.html', 
                         usage_history=usage_history, 
                         user=user)

