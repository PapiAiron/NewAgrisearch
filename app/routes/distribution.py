"""
Event-Based Distribution Routes - Simplified Workflow
Request → Event Allocation → Officer Distribution → Farmer Verification
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app import db
from app.models.user import User
from app.models.farm import Farm
from app.models.distribution import (
    DistributionRequest, DistributionEvent, DistributionRecord,
    MunicipalOffer, MunicipalOfferClaim
)
from functools import wraps
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)
distribution_bp = Blueprint('distribution', __name__)

SUPPLY_TYPES = {
    'fertilizer': 'Fertilizers',
    'feed': 'Animal Feed',
    'fingerling': 'Fingerlings',
    'seed': 'Plant Seeds',
    'pesticide': 'Pesticides',
    'other': 'Other'
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if user.role not in ['victoria_admin', 'system_admin']:
            flash('Not authorized', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated

# ===== FARMER ROUTES =====

@distribution_bp.route('/my-requests', methods=['GET'])
@login_required
def my_requests():
    """View farmer's distribution requests"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can view requests', 'warning')
        return redirect(url_for('dashboard.index'))
    
    # Get farmer's farms
    farms = Farm.query.filter_by(owner_id=user.id).all()
    farm_ids = [f.id for f in farms]
    
    # Get status filter from query parameter
    status_filter = request.args.get('status', '')
    
    # Get all requests from these farms
    query = DistributionRequest.query.filter(
        DistributionRequest.farm_id.in_(farm_ids)
    )
    
    # If status filter provided, apply it
    if status_filter:
        query = query.filter(DistributionRequest.status == status_filter)
    
    requests = query.order_by(DistributionRequest.requested_at.desc()).all()
    
    return render_template('distribution/farmer/my_requests.html', requests=requests, supplies=SUPPLY_TYPES)

@distribution_bp.route('/request/new', methods=['GET', 'POST'])
@login_required
def create_request():
    """Farmer creates a new distribution request"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can create requests', 'warning')
        return redirect(url_for('dashboard.index'))
    
    farms = Farm.query.filter_by(owner_id=user.id).all()
    
    if request.method == 'POST':
        farm_id = request.form.get('farm_id', type=int)
        supply_type = request.form.get('supply_type', '').strip()
        # If farmer typed a custom category (Other selected), use that value
        if supply_type == 'other' or not supply_type:
            supply_type = request.form.get('supply_type_other', '').strip() or supply_type
        supply_name = request.form.get('supply_name')
        quantity = request.form.get('quantity', type=float)
        unit = request.form.get('unit')
        reason = request.form.get('reason')
        request_type = 'direct_municipal'
        
        # Verify farm ownership
        farm = Farm.query.get(farm_id)
        if not farm or farm.owner_id != user.id:
            flash('Invalid farm', 'danger')
            return redirect(url_for('distribution.create_request'))
        
        try:
            req = DistributionRequest(
                farm_id=farm_id,
                supply_type=supply_type,
                supply_name=supply_name,
                quantity_requested=quantity,
                unit=unit,
                reason=reason,
                requested_by_id=user.id,
                request_type=request_type,
                status='pending'
            )
            db.session.add(req)
            db.session.commit()
            logger.info(f"[DISTRIBUTION] New direct request created by user {user.id}")
            
            flash('Your request has been sent directly to the Municipal Office.', 'success')
            return redirect(url_for('distribution.my_requests'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[DISTRIBUTION] Error creating request: {str(e)}", exc_info=True)
            flash(f'Error creating distribution request: {str(e)}', 'danger')
            return redirect(url_for('distribution.create_request'))
    
    return render_template('distribution/farmer/request.html', farms=farms, supply_types=SUPPLY_TYPES, cycles=[])

@distribution_bp.route('/request/<int:req_id>', methods=['GET'])
@login_required
def view_request(req_id):
    """View single request details with distribution status"""
    req = DistributionRequest.query.get_or_404(req_id)
    
    # Check access
    user = User.query.get(session['user_id'])
    if user.role == 'farmer' and req.requested_by_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Get distribution record if exists
    record = req.get_latest_record()
    
    # Redirect farmers to their requests list; staff can view via admin pages
    return redirect(url_for('distribution.my_requests'))

@distribution_bp.route('/received', methods=['GET'], endpoint='received_supplies')
@login_required
def received_supplies():
    """View farmer's received and verified distributions"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can view received supplies', 'warning')
        return redirect(url_for('dashboard.index'))
    
    # Get farmer's farms
    farms = Farm.query.filter_by(owner_id=user.id).all()
    farm_ids = [f.id for f in farms]
    
    # Get all verified distribution records for these farms
    records = DistributionRecord.query.filter(
        DistributionRecord.request_id.in_(
            db.session.query(DistributionRequest.id).filter(
                DistributionRequest.farm_id.in_(farm_ids)
            )
        ),
        DistributionRecord.status == 'verified'
    ).order_by(DistributionRecord.verified_at.desc()).all()
    
    return render_template('distribution/farmer/received_distributions.html', distributions=records)

@distribution_bp.route('/verify/<int:record_id>', methods=['GET', 'POST'])
@login_required
def verify_receipt(record_id):
    """Farmer verifies receipt of distributed items"""
    record = DistributionRecord.query.get_or_404(record_id)
    user = User.query.get(session['user_id'])
    
    # Verify authorization
    if user.role != 'farmer' or record.request.requested_by_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if not record.can_be_verified():
        flash('This distribution cannot be verified yet', 'warning')
        return redirect(url_for('distribution.view_request', req_id=record.request_id))
    
    if request.method == 'POST':
        provided_code = request.form.get('code', '').strip().upper()
        notes = request.form.get('notes', '')
        
        if provided_code != record.verification_code:
            flash('Invalid verification code', 'danger')
            return redirect(url_for('distribution.verify_receipt', record_id=record_id))
        
        try:
            record.status = 'verified'
            record.verified_at = datetime.utcnow()
            record.verified_by_id = user.id
            record.verification_notes = notes
            record.updated_at = datetime.utcnow()
            
            req = record.request
            req.status = 'fulfilled'
            
            db.session.commit()
            logger.info(f"[DISTRIBUTION] Distribution {record_id} verified by farmer {user.id}")
            
            flash('Distribution verified successfully!', 'success')
            return redirect(url_for('distribution.view_request', req_id=record.request_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[DISTRIBUTION] Error verifying receipt: {str(e)}", exc_info=True)
            flash(f'Error verifying receipt: {str(e)}', 'danger')
            return redirect(url_for('distribution.verify_receipt', record_id=record_id))
    
    return render_template('distribution/farmer/verify.html', record=record)

# ===== OFFICER ROUTES =====

# ===== ADMIN ROUTES (Victoria Admin & System Admin) =====

@distribution_bp.route('/admin/events', methods=['GET'], endpoint='list_cycles')
@admin_required
def admin_events():
    """View all distribution events"""
    events = DistributionEvent.query.order_by(
        DistributionEvent.scheduled_date.desc()
    ).all()
    
    return render_template('distribution/admin/cycles.html', cycles=events)

@distribution_bp.route('/admin/event/create', methods=['GET', 'POST'])
@admin_required
def create_event():
    """Create new distribution event"""
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        location = request.form.get('location')
        barangay = request.form.get('barangay')
        scheduled_date = request.form.get('scheduled_date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        
        event = DistributionEvent(
            name=name,
            description=description,
            location=location,
            barangay=barangay,
            scheduled_date=scheduled_date,
            start_time=start_time if start_time else None,
            end_time=end_time if end_time else None,
            created_by_id=user.id,
            status='planned'
        )
        db.session.add(event)
        db.session.commit()
        
        flash('Distribution event created', 'success')
        return redirect(url_for('distribution.list_cycles'))
    
    return render_template('distribution/admin/create_cycle.html')

@distribution_bp.route('/admin/event/<int:event_id>/allocate', methods=['GET', 'POST'])
@admin_required
def allocate_to_event(event_id):
    """Allocate approved requests to distribution event"""
    event = DistributionEvent.query.get_or_404(event_id)
    
    if request.method == 'POST':
        req_id = request.form.get('request_id', type=int)
        quantity = request.form.get('quantity', type=float)
        
        req = DistributionRequest.query.get(req_id)
        if not req or req.status != 'approved':
            flash('Invalid or unapproved request', 'danger')
            return redirect(url_for('distribution.allocate_to_event', event_id=event_id))
        
        record = DistributionRecord(
            request_id=req_id,
            event_id=event_id,
            quantity_distributed=quantity,
            status='allocated'
        )
        db.session.add(record)
        db.session.commit()
        
        flash('Request allocated to event', 'success')
        return redirect(url_for('distribution.event_detail', event_id=event_id))
    
    # Get only admin-approved requests for this event's barangay (not yet allocated)
    allocated_req_ids = db.session.query(DistributionRecord.request_id).filter(
        DistributionRecord.event_id == event_id
    ).subquery()
    approved_requests = DistributionRequest.query.filter(
        DistributionRequest.status == 'approved',
        ~DistributionRequest.id.in_(allocated_req_ids)
    ).join(Farm).filter(
        Farm.barangay_name == event.barangay
    ).all()
    existing_records = event.distribution_records
    
    return render_template('distribution/admin/plan_distribution.html',
                           cycle=event, requests=approved_requests,
                           distributions=existing_records, supply_types=SUPPLY_TYPES)

@distribution_bp.route('/admin/event/<int:event_id>/detail', methods=['GET'])
@admin_required
def event_detail(event_id):
    """View event details with allocated distributions"""
    event = DistributionEvent.query.get_or_404(event_id)
    records = event.distribution_records
    total = len(records)
    summary = {
        'total': total,
        'allocated': sum(1 for r in records if r.status == 'allocated'),
        'distributed': sum(1 for r in records if r.status == 'distributed'),
        'verified': sum(1 for r in records if r.status == 'verified'),
    }
    return render_template('distribution/admin/view_cycle.html',
                           cycle=event, distributions=records, summary=summary)

# ===== ADMIN APPROVAL ROUTES =====

@distribution_bp.route('/admin/requests', methods=['GET'], endpoint='admin_approval_requests')
@admin_required
def admin_approval_requests():
    """Victoria admin reviews officer-recommended requests and gives final approval"""
    user = User.query.get(session['user_id'])
    pending = DistributionRequest.query.filter(
        DistributionRequest.status == 'officer_approved'
    ).order_by(DistributionRequest.requested_at.desc()).all()
    return render_template('distribution/admin/approve_requests.html',
                           requests=pending, user=user, supply_types=SUPPLY_TYPES)

@distribution_bp.route('/admin/requests/<int:req_id>/decide', methods=['POST'])
@admin_required
def admin_decide_request(req_id):
    """Victoria admin approves or rejects an officer-recommended request"""
    req = DistributionRequest.query.get_or_404(req_id)
    user = User.query.get(session['user_id'])
    action = request.form.get('action')
    notes = request.form.get('admin_notes', '')

    try:
        if action == 'approve':
            req.status = 'approved'
            flash(f'Request for {req.supply_name} approved — ready for allocation.', 'success')
        else:
            req.status = 'rejected'
            flash(f'Request for {req.supply_name} rejected.', 'warning')

        if notes:
            req.officer_notes = (req.officer_notes or '') + f'\n[Admin] {notes}'
        db.session.commit()
        logger.info(f"[DISTRIBUTION] Admin {user.id} {action}d request {req_id}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[DISTRIBUTION] Error deciding request: {str(e)}", exc_info=True)
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('distribution.admin_approval_requests'))

# ===== API Routes =====

@distribution_bp.route('/api/requests/pending', methods=['GET'])
@login_required
def api_pending_requests():
    """Get pending requests count"""
    user = User.query.get(session['user_id'])
    
    if user.role == 'farmer':
        farms = Farm.query.filter_by(owner_id=user.id).all()
        farm_ids = [f.id for f in farms]
        count = DistributionRequest.query.filter(
            DistributionRequest.farm_id.in_(farm_ids),
            DistributionRequest.status != 'fulfilled'
        ).count()
    else:
        count = DistributionRequest.query.filter(
            DistributionRequest.status == 'pending'
        ).count()
    
    return jsonify({'count': count})


@distribution_bp.route('/api/direct-requests/count', methods=['GET'])
@login_required
def api_direct_requests_count():
    """Get pending direct_municipal requests count (for admin badge)"""
    user = User.query.get(session['user_id'])
    if user.role not in ['victoria_admin', 'system_admin']:
        return jsonify({'count': 0})
    count = DistributionRequest.query.filter(
        DistributionRequest.status == 'pending',
        DistributionRequest.request_type == 'direct_municipal'
    ).count()
    return jsonify({'count': count})


@distribution_bp.route('/api/open-offers/count', methods=['GET'])
@login_required
def api_open_offers_count():
    """Get open municipal offers count for farmer's barangay (for sidebar badge)"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        return jsonify({'count': 0})
    farms = Farm.query.filter_by(owner_id=user.id).all()
    barangays = list({f.barangay_name for f in farms})
    from datetime import date
    today = date.today()
    count = MunicipalOffer.query.filter(
        MunicipalOffer.status == 'open',
        MunicipalOffer.claim_deadline >= today,
        db.or_(
            MunicipalOffer.target_barangay == None,
            MunicipalOffer.target_barangay.in_(barangays)
        )
    ).count()
    return jsonify({'count': count})


# ===== FARMER — AVAILABLE OFFERS =====

@distribution_bp.route('/available-offers', methods=['GET'])
@login_required
def available_offers():
    """List open municipal offers for farmer to register"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can view available offers', 'warning')
        return redirect(url_for('dashboard.index'))

    farms = Farm.query.filter_by(owner_id=user.id).all()
    barangays = list({f.barangay_name for f in farms})

    from datetime import date
    today = date.today()
    offers = MunicipalOffer.query.filter(
        MunicipalOffer.status == 'open',
        MunicipalOffer.claim_deadline >= today,
        db.or_(
            MunicipalOffer.target_barangay == None,
            MunicipalOffer.target_barangay.in_(barangays)
        )
    ).order_by(MunicipalOffer.claim_deadline).all()

    # Figure out which offers the farmer already registered for
    registered_offer_ids = {
        c.offer_id for c in MunicipalOfferClaim.query.filter_by(farmer_id=user.id).all()
    }

    return render_template('distribution/farmer/available_offers.html',
                           offers=offers, farms=farms,
                           registered_offer_ids=registered_offer_ids,
                           supply_types=SUPPLY_TYPES)


@distribution_bp.route('/offers/<int:offer_id>/register', methods=['POST'])
@login_required
def register_for_offer(offer_id):
    """Farmer registers interest in a municipal offer"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can register for offers', 'warning')
        return redirect(url_for('dashboard.index'))

    offer = MunicipalOffer.query.get_or_404(offer_id)

    if offer.status != 'open':
        flash('This offer is no longer accepting registrations', 'warning')
        return redirect(url_for('distribution.available_offers'))

    farm_id = request.form.get('farm_id', type=int)
    farm = Farm.query.get(farm_id)
    if not farm or farm.owner_id != user.id:
        flash('Invalid farm selection', 'danger')
        return redirect(url_for('distribution.available_offers'))

    # Prevent duplicate registration per (offer, farmer)
    existing = MunicipalOfferClaim.query.filter_by(offer_id=offer_id, farmer_id=user.id).first()
    if existing:
        flash('You have already registered for this offer', 'warning')
        return redirect(url_for('distribution.my_claims'))

    try:
        claim = MunicipalOfferClaim(
            offer_id=offer_id,
            farm_id=farm_id,
            farmer_id=user.id,
            quantity_reserved=offer.quantity_per_farmer,
            status='registered'
        )
        claim.generate_claim_code()
        db.session.add(claim)
        db.session.commit()
        logger.info(f"[DISTRIBUTION] Farmer {user.id} registered for offer {offer_id}")
        flash(f'Registered! Your claim code is: {claim.claim_code}', 'success')
        return redirect(url_for('distribution.my_claims'))
    except Exception as e:
        db.session.rollback()
        logger.error(f"[DISTRIBUTION] Error registering for offer: {str(e)}", exc_info=True)
        flash(f'Error registering: {str(e)}', 'danger')
        return redirect(url_for('distribution.available_offers'))


@distribution_bp.route('/my-claims', methods=['GET'])
@login_required
def my_claims():
    """Farmer's registered offer claims"""
    user = User.query.get(session['user_id'])
    if user.role != 'farmer':
        flash('Only farmers can view their claims', 'warning')
        return redirect(url_for('dashboard.index'))

    claims = MunicipalOfferClaim.query.filter_by(farmer_id=user.id).order_by(
        MunicipalOfferClaim.registered_at.desc()
    ).all()
    return render_template('distribution/farmer/my_claims.html', claims=claims)


# ===== ADMIN — DIRECT REQUESTS =====

@distribution_bp.route('/admin/direct-requests', methods=['GET'])
@admin_required
def admin_direct_requests():
    """Victoria admin views direct-to-municipal pending requests"""
    user = User.query.get(session['user_id'])
    status_filter = request.args.get('status', 'pending')
    query = DistributionRequest.query.filter(
        DistributionRequest.request_type == 'direct_municipal'
    )
    if status_filter:
        query = query.filter(DistributionRequest.status == status_filter)
    requests = query.order_by(DistributionRequest.requested_at.desc()).all()
    return render_template('distribution/admin/direct_requests.html',
                           requests=requests, supply_types=SUPPLY_TYPES,
                           status_filter=status_filter, user=user)


@distribution_bp.route('/admin/direct-requests/<int:req_id>/approve', methods=['POST'])
@admin_required
def admin_approve_direct_request(req_id):
    """Admin approves direct request and sets pickup details + generates claim code"""
    req = DistributionRequest.query.get_or_404(req_id)
    if req.request_type != 'direct_municipal' or req.status != 'pending':
        flash('Invalid request', 'danger')
        return redirect(url_for('distribution.admin_direct_requests'))

    claim_location = request.form.get('claim_location', '').strip()
    claim_deadline_str = request.form.get('claim_deadline', '').strip()
    admin_notes = request.form.get('admin_notes', '').strip()

    if not claim_location or not claim_deadline_str:
        flash('Claim location and deadline are required', 'danger')
        return redirect(url_for('distribution.admin_direct_requests'))

    try:
        from datetime import date
        req.status = 'ready_to_claim'
        req.claim_location = claim_location
        req.claim_deadline = datetime.strptime(claim_deadline_str, '%Y-%m-%d').date()
        req.claim_code = secrets.token_hex(5).upper()
        if admin_notes:
            req.officer_notes = admin_notes
        db.session.commit()
        logger.info(f"[DISTRIBUTION] Admin approved direct request {req_id}, code={req.claim_code}")
        flash(f'Request approved. Claim code: {req.claim_code}', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"[DISTRIBUTION] Error approving direct request: {str(e)}", exc_info=True)
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('distribution.admin_direct_requests'))


@distribution_bp.route('/admin/direct-requests/<int:req_id>/reject', methods=['POST'])
@admin_required
def admin_reject_direct_request(req_id):
    """Admin rejects a direct request"""
    req = DistributionRequest.query.get_or_404(req_id)
    if req.request_type != 'direct_municipal':
        flash('Invalid request', 'danger')
        return redirect(url_for('distribution.admin_direct_requests'))
    try:
        req.status = 'rejected'
        req.officer_notes = request.form.get('admin_notes', '')
        db.session.commit()
        flash('Request rejected.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('distribution.admin_direct_requests'))


@distribution_bp.route('/admin/direct-requests/<int:req_id>/claim', methods=['POST'])
@admin_required
def admin_mark_direct_claimed(req_id):
    """Admin marks a ready_to_claim request as claimed (farmer picked it up)"""
    req = DistributionRequest.query.get_or_404(req_id)
    if req.status != 'ready_to_claim':
        flash('Request is not ready to claim', 'warning')
        return redirect(url_for('distribution.admin_direct_requests', status='ready_to_claim'))
    try:
        req.status = 'claimed'
        db.session.commit()
        flash('Marked as claimed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('distribution.admin_direct_requests', status='ready_to_claim'))


# ===== ADMIN — MUNICIPAL OFFERS =====

BARANGAYS = [
    'Banca-Banca', 'Daniw', 'Masapang', 'Nanhaya', 'Pagalangan',
    'San Benito', 'San Felix', 'San Francisco', 'San Roque'
]


@distribution_bp.route('/admin/offers', methods=['GET'])
@admin_required
def admin_offers():
    """Admin lists all municipal offers"""
    user = User.query.get(session['user_id'])
    offers = MunicipalOffer.query.order_by(MunicipalOffer.created_at.desc()).all()
    return render_template('distribution/admin/offers.html',
                           offers=offers, supply_types=SUPPLY_TYPES,
                           barangays=BARANGAYS, user=user)


@distribution_bp.route('/admin/offers/create', methods=['POST'])
@admin_required
def admin_create_offer():
    """Admin creates a new municipal offer"""
    user = User.query.get(session['user_id'])
    name = request.form.get('name', '').strip()
    supply_name = request.form.get('supply_name', '').strip()
    supply_type = request.form.get('supply_type', '').strip()
    total_quantity = request.form.get('total_quantity', type=float)
    quantity_per_farmer = request.form.get('quantity_per_farmer', type=float)
    unit = request.form.get('unit', '').strip()
    claim_location = request.form.get('claim_location', '').strip()
    claim_start_str = request.form.get('claim_start', '').strip()
    claim_deadline_str = request.form.get('claim_deadline', '').strip()
    target_barangay = request.form.get('target_barangay', '').strip() or None
    notes = request.form.get('notes', '').strip()

    if not all([name, supply_name, supply_type, total_quantity, quantity_per_farmer, unit, claim_location, claim_deadline_str]):
        flash('Please fill in all required fields', 'danger')
        return redirect(url_for('distribution.admin_offers'))

    try:
        offer = MunicipalOffer(
            name=name,
            supply_name=supply_name,
            supply_type=supply_type,
            total_quantity=total_quantity,
            quantity_per_farmer=quantity_per_farmer,
            unit=unit,
            claim_location=claim_location,
            claim_start=datetime.strptime(claim_start_str, '%Y-%m-%d').date() if claim_start_str else None,
            claim_deadline=datetime.strptime(claim_deadline_str, '%Y-%m-%d').date(),
            target_barangay=target_barangay,
            notes=notes,
            status='draft',
            created_by_id=user.id
        )
        db.session.add(offer)
        db.session.commit()
        flash('Municipal offer created (status: Draft). Open it when ready.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"[DISTRIBUTION] Error creating offer: {str(e)}", exc_info=True)
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('distribution.admin_offers'))


@distribution_bp.route('/admin/offers/<int:offer_id>/open', methods=['POST'])
@admin_required
def admin_open_offer(offer_id):
    """Open an offer so farmers can register"""
    offer = MunicipalOffer.query.get_or_404(offer_id)
    try:
        offer.status = 'open'
        db.session.commit()
        flash(f'Offer "{offer.name}" is now open to farmers.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('distribution.admin_offers'))


@distribution_bp.route('/admin/offers/<int:offer_id>/close', methods=['POST'])
@admin_required
def admin_close_offer(offer_id):
    """Close an offer"""
    offer = MunicipalOffer.query.get_or_404(offer_id)
    try:
        offer.status = 'closed'
        db.session.commit()
        flash(f'Offer "{offer.name}" closed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('distribution.admin_offers'))


@distribution_bp.route('/admin/offers/<int:offer_id>/claims', methods=['GET'])
@admin_required
def admin_offer_claims(offer_id):
    """Admin views registrations for a specific offer"""
    offer = MunicipalOffer.query.get_or_404(offer_id)
    claims = MunicipalOfferClaim.query.filter_by(offer_id=offer_id).order_by(
        MunicipalOfferClaim.registered_at
    ).all()
    return render_template('distribution/admin/offer_claims.html', offer=offer, claims=claims)


@distribution_bp.route('/admin/offers/<int:offer_id>/claims/<int:claim_id>/mark', methods=['POST'])
@admin_required
def admin_mark_offer_claim(offer_id, claim_id):
    """Admin marks an offer claim as claimed or no_show"""
    claim = MunicipalOfferClaim.query.get_or_404(claim_id)
    if claim.offer_id != offer_id:
        flash('Invalid claim', 'danger')
        return redirect(url_for('distribution.admin_offer_claims', offer_id=offer_id))

    action = request.form.get('action')
    try:
        if action == 'claimed':
            claim.status = 'claimed'
            claim.claimed_at = datetime.utcnow()
            flash(f'Claim for {claim.farmer.full_name} marked as claimed.', 'success')
        elif action == 'no_show':
            claim.status = 'no_show'
            flash(f'Claim for {claim.farmer.full_name} marked as no-show.', 'warning')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('distribution.admin_offer_claims', offer_id=offer_id))
