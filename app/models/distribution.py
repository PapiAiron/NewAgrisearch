"""
Municipal Supply Distribution System Models - Event-Based with Verification
Simplified workflow: Farmers submit requests → Events scheduled → Officer distributes → Farmer verifies
"""
from app import db
from datetime import datetime
import secrets


class DistributionRequest(db.Model):
    """Farmer request for supplies - direct requests without cycles"""
    __tablename__ = 'distribution_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    farm = db.relationship('Farm', backref=db.backref('distribution_requests', lazy=True))
    
    # Request details
    supply_type = db.Column(db.String(100), nullable=False)  # fertilizer, feed, seeds, fingerlings
    supply_name = db.Column(db.String(200), nullable=False)
    quantity_requested = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)  # kg, bags, liters, pieces
    reason = db.Column(db.Text)
    
    # Status: pending, approved, rejected, fulfilled, ready_to_claim, claimed
    status = db.Column(db.String(50), default='pending')

    # Request type: 'via_officer' (default) or 'direct_municipal'
    request_type = db.Column(db.String(50), default='via_officer')

    # Claim details (populated by admin when direct request is approved)
    claim_code = db.Column(db.String(10))
    claim_location = db.Column(db.String(200))
    claim_deadline = db.Column(db.Date)

    # Who's involved
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])
    
    reviewed_by_officer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_by_officer = db.relationship('User', foreign_keys=[reviewed_by_officer_id])
    officer_review_date = db.Column(db.DateTime)
    officer_notes = db.Column(db.Text)
    
    # Timestamps
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    distribution_records = db.relationship('DistributionRecord', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('ix_distribution_requests_status', 'status'),
        db.Index('ix_distribution_requests_farm_id', 'farm_id'),
    )
    
    def __repr__(self):
        return f'<DistributionRequest {self.supply_name} - {self.status}>'
    
    def is_pending(self):
        return self.status == 'pending'
    
    def is_approved(self):
        return self.status == 'approved'
    
    def get_latest_record(self):
        if self.distribution_records:
            return max(self.distribution_records, key=lambda r: r.created_at)
        return None


class DistributionEvent(db.Model):
    """Distribution event - scheduled by Victoria Admin for when/where distribution happens"""
    __tablename__ = 'distribution_events'
    
    id = db.Column(db.Integer, primary_key=True)
    
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(300), nullable=False)
    barangay = db.Column(db.String(100), nullable=False)
    
    scheduled_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    
    status = db.Column(db.String(50), default='planned')  # planned, ongoing, completed, cancelled
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref=db.backref('distribution_events_created', lazy=True))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    distribution_records = db.relationship('DistributionRecord', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('ix_distribution_events_status', 'status'),
        db.Index('ix_distribution_events_scheduled_date', 'scheduled_date'),
        db.Index('ix_distribution_events_barangay', 'barangay'),
    )
    
    def __repr__(self):
        return f'<DistributionEvent {self.name}>'
    
    def get_summary(self):
        """Get event summary with distribution counts"""
        total = len(self.distribution_records)
        distributed = len([r for r in self.distribution_records if r.status in ['distributed', 'verified']])
        verified = len([r for r in self.distribution_records if r.status == 'verified'])
        return {'total': total, 'distributed': distributed, 'verified': verified, 'pending': total - distributed}


class DistributionRecord(db.Model):
    """Actual distribution record - tracks request fulfillment with officer & farmer verification"""
    __tablename__ = 'distribution_records'
    
    id = db.Column(db.Integer, primary_key=True)
    
    request_id = db.Column(db.Integer, db.ForeignKey('distribution_requests.id'), nullable=False)
    request = db.relationship('DistributionRequest', foreign_keys=[request_id], overlaps='distribution_records')
    
    event_id = db.Column(db.Integer, db.ForeignKey('distribution_events.id'), nullable=False)
    event = db.relationship('DistributionEvent', foreign_keys=[event_id], overlaps='distribution_records')
    
    quantity_distributed = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text)
    
    # Status flow: allocated → distributed → verified
    status = db.Column(db.String(50), default='allocated')
    
    # Officer distribution
    distributed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    distributed_by = db.relationship('User', foreign_keys=[distributed_by_id], backref=db.backref('distributions_made', lazy=True))
    distribution_time = db.Column(db.DateTime)
    
    # Farmer verification
    verification_code = db.Column(db.String(10), unique=True)
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_by = db.relationship('User', foreign_keys=[verified_by_id], backref=db.backref('distributions_verified', lazy=True))
    verification_notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('ix_distribution_records_status', 'status'),
        db.Index('ix_distribution_records_request_id', 'request_id'),
        db.Index('ix_distribution_records_event_id', 'event_id'),
        db.Index('ix_distribution_records_verification_code', 'verification_code'),
    )
    
    def __repr__(self):
        return f'<DistributionRecord {self.quantity_distributed} {self.request.unit}>'
    
    def is_verified(self):
        return self.status == 'verified'
    
    def is_distributed(self):
        return self.status in ['distributed', 'verified']
    
    def generate_verification_code(self):
        code = secrets.token_hex(5).upper()
        self.verification_code = code
        return code
    
    def can_be_verified(self):
        return self.status == 'distributed' and self.verification_code is not None
    
    def get_status_label(self):
        labels = {
            'allocated': 'Allocated to Event',
            'distributed': 'Distributed by Officer',
            'verified': 'Confirmed by Farmer'
        }
        return labels.get(self.status, self.status)


class MunicipalOffer(db.Model):
    """Admin-created push offer — supplies available for farmers to register and claim"""
    __tablename__ = 'municipal_offers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    supply_name = db.Column(db.String(200), nullable=False)
    supply_type = db.Column(db.String(100), nullable=False)
    total_quantity = db.Column(db.Float, nullable=False)
    quantity_per_farmer = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)

    claim_location = db.Column(db.String(200), nullable=False)
    claim_start = db.Column(db.Date)
    claim_deadline = db.Column(db.Date, nullable=False)

    # nullable = open to all barangays
    target_barangay = db.Column(db.String(100))
    notes = db.Column(db.Text)

    # status: draft → open → closed
    status = db.Column(db.String(50), default='draft')

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref=db.backref('municipal_offers_created', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    claims = db.relationship('MunicipalOfferClaim', backref='offer', lazy=True, cascade='all, delete-orphan')

    def registered_count(self):
        return len([c for c in self.claims if c.status != 'no_show'])

    def __repr__(self):
        return f'<MunicipalOffer {self.name} [{self.status}]>'


class MunicipalOfferClaim(db.Model):
    """Farmer's registration to claim a municipal offer"""
    __tablename__ = 'municipal_offer_claims'

    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey('municipal_offers.id'), nullable=False)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    quantity_reserved = db.Column(db.Float, nullable=False)
    claim_code = db.Column(db.String(10), unique=True)

    # status: registered → claimed | no_show
    status = db.Column(db.String(50), default='registered')

    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    claimed_at = db.Column(db.DateTime)

    farm = db.relationship('Farm', foreign_keys=[farm_id])
    farmer = db.relationship('User', foreign_keys=[farmer_id], backref=db.backref('offer_claims', lazy=True))

    def generate_claim_code(self):
        code = secrets.token_hex(5).upper()
        self.claim_code = code
        return code

    def __repr__(self):
        return f'<MunicipalOfferClaim offer={self.offer_id} farmer={self.farmer_id} [{self.status}]>'
