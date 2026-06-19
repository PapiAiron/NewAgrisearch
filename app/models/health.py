"""
Phase 4 - Health Management Models
Enhanced vaccine, disease, and health tracking
"""
from app import db
from datetime import datetime, timedelta


class VaccineInventory(db.Model):
    """Vaccine inventory tracking - Phase 4"""
    __tablename__ = 'vaccine_inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    farm = db.relationship('Farm', backref=db.backref('vaccine_inventory', lazy=True))
    
    # Vaccine information
    vaccine_name = db.Column(db.String(200), nullable=False)  # e.g., "FMD Vaccine", "Rabies"
    vaccine_code = db.Column(db.String(100))  # Batch/lot number
    description = db.Column(db.Text)
    
    # Inventory tracking
    quantity_units = db.Column(db.Integer, nullable=False)  # Number of units (doses, vials, etc.)
    unit_type = db.Column(db.String(50), default='dose')  # dose, vial, bottle, etc.
    quantity_used = db.Column(db.Integer, default=0)
    
    # Storage
    storage_location = db.Column(db.String(200))  # Refrigerator, freezer, etc.
    storage_temperature = db.Column(db.String(100))  # 2-8°C, -20°C, etc.
    
    # Dates
    purchase_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=False)
    opened_date = db.Column(db.DateTime)
    
    # Cost
    cost_per_unit = db.Column(db.Float)
    total_cost = db.Column(db.Float)
    
    # Supplier
    supplier_name = db.Column(db.String(200))
    supplier_contact = db.Column(db.String(200))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_vaccine_farm_id', 'farm_id'),
        db.Index('ix_vaccine_expiry_date', 'expiry_date'),
        db.Index('ix_vaccine_is_active', 'is_active'),
    )
    
    def __repr__(self):
        return f'<VaccineInventory {self.vaccine_name}>'
    
    @property
    def quantity_remaining(self):
        """Calculate remaining quantity"""
        return self.quantity_units - self.quantity_used
    
    @property
    def is_expired(self):
        """Check if vaccine is expired"""
        if not self.expiry_date:
            return False
        return self.expiry_date < datetime.utcnow()
    
    @property
    def days_until_expiry(self):
        """Get days until expiry"""
        if not self.expiry_date:
            return 999  # Very far in future if no expiry date
        delta = self.expiry_date - datetime.utcnow()
        return delta.days
    
    @property
    def expiry_status(self):
        """Get expiry status"""
        if not self.expiry_date:
            return 'unknown'  # No expiry date set
        days = self.days_until_expiry
        if days < 0:
            return 'expired'
        elif days < 7:
            return 'expiring_soon'
        elif days < 30:
            return 'caution'
        return 'good'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'farm_id': self.farm_id,
            'vaccine_name': self.vaccine_name,
            'vaccine_code': self.vaccine_code,
            'quantity_units': self.quantity_units,
            'quantity_remaining': self.quantity_remaining,
            'unit_type': self.unit_type,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'is_expired': self.is_expired,
            'cost_per_unit': self.cost_per_unit,
            'total_cost': self.total_cost,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DiseaseRecord(db.Model):
    """Disease and illness tracking - Phase 4"""
    __tablename__ = 'disease_records'
    
    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)
    livestock = db.relationship('Livestock', backref=db.backref('diseases', lazy=True))
    
    # Disease information
    disease_name = db.Column(db.String(200), nullable=False)  # e.g., "Foot and Mouth Disease"
    disease_code = db.Column(db.String(100))  # Clinical code or reference
    description = db.Column(db.Text)
    severity = db.Column(db.String(50))  # mild, moderate, severe, critical
    
    # Timeline
    onset_date = db.Column(db.DateTime, nullable=False)  # When disease started
    diagnosis_date = db.Column(db.DateTime)  # When it was diagnosed
    treatment_start_date = db.Column(db.DateTime)
    recovery_date = db.Column(db.DateTime)  # When animal recovered
    
    # Medical details
    symptoms = db.Column(db.Text)  # Description of symptoms
    diagnosis_method = db.Column(db.String(200))  # Lab test, clinical exam, etc.
    
    # Treatment
    treatment_given = db.Column(db.Text)  # What was done
    medications_used = db.Column(db.Text)  # Medicines given
    veterinarian_name = db.Column(db.String(200))
    clinic_name = db.Column(db.String(200))
    
    # Outcome
    outcome = db.Column(db.String(50))  # recovered, ongoing, deceased
    notes = db.Column(db.Text)
    
    # Cost
    treatment_cost = db.Column(db.Float)
    medication_cost = db.Column(db.Float)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_disease_livestock_id', 'livestock_id'),
        db.Index('ix_disease_onset_date', 'onset_date'),
        db.Index('ix_disease_outcome', 'outcome'),
    )
    
    def __repr__(self):
        return f'<DiseaseRecord {self.disease_name}>'
    
    @property
    def duration_days(self):
        """Calculate disease duration in days"""
        end_date = self.recovery_date or datetime.utcnow()
        delta = end_date - self.onset_date
        return delta.days
    
    @property
    def is_active(self):
        """Check if disease is still active"""
        return self.outcome == 'ongoing'
    
    @property
    def total_cost(self):
        """Calculate total treatment cost"""
        treatment = self.treatment_cost or 0
        medication = self.medication_cost or 0
        return treatment + medication
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'livestock_id': self.livestock_id,
            'disease_name': self.disease_name,
            'severity': self.severity,
            'onset_date': self.onset_date.isoformat() if self.onset_date else None,
            'outcome': self.outcome,
            'duration_days': self.duration_days,
            'treatment_cost': self.treatment_cost,
            'medication_cost': self.medication_cost,
            'total_cost': self.total_cost,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class HealthAlert(db.Model):
    """Health alerts and compliance tracking - Phase 4"""
    __tablename__ = 'health_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)
    livestock = db.relationship('Livestock', backref=db.backref('health_alerts', lazy=True))
    
    # Alert information
    alert_type = db.Column(db.String(50), nullable=False)  # vaccine_due, treatment_due, checkup_due, disease_risk
    alert_title = db.Column(db.String(200), nullable=False)
    alert_message = db.Column(db.Text)
    
    # Priority
    priority = db.Column(db.String(50), default='medium')  # low, medium, high, critical
    
    # Timeline
    alert_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)  # When action is due
    resolved_date = db.Column(db.DateTime)
    
    # Status
    is_resolved = db.Column(db.Boolean, default=False)
    resolution_notes = db.Column(db.Text)
    
    # Related data
    related_record_id = db.Column(db.Integer)  # ID of related health/vaccine record
    related_record_type = db.Column(db.String(50))  # health_record, disease, etc.
    
    # Notification
    notification_sent = db.Column(db.Boolean, default=False)
    notification_method = db.Column(db.String(50))  # email, sms, in_app
    notification_date = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_alert_livestock_id', 'livestock_id'),
        db.Index('ix_alert_type', 'alert_type'),
        db.Index('ix_alert_priority', 'priority'),
        db.Index('ix_alert_is_resolved', 'is_resolved'),
    )
    
    def __repr__(self):
        return f'<HealthAlert {self.alert_title}>'
    
    @property
    def is_overdue(self):
        """Check if alert is overdue"""
        if self.due_date and self.due_date < datetime.utcnow():
            if not self.is_resolved:
                return True
        return False
    
    @property
    def days_overdue(self):
        """Get days overdue"""
        if self.is_overdue:
            delta = datetime.utcnow() - self.due_date
            return delta.days
        return 0
    
    @property
    def days_until_due(self):
        """Get days until due"""
        if self.due_date and not self.is_resolved:
            delta = self.due_date - datetime.utcnow()
            return delta.days
        return None
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'livestock_id': self.livestock_id,
            'alert_type': self.alert_type,
            'alert_title': self.alert_title,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'is_resolved': self.is_resolved,
            'is_overdue': self.is_overdue,
            'notification_sent': self.notification_sent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
