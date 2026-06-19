"""
Livestock and animal management models
"""
from app import db
from datetime import datetime
from enum import Enum

class AnimalType(Enum):
    """Animal type enumeration"""
    CATTLE = 'cattle'
    PIG = 'pig'
    GOAT = 'goat'
    CHICKEN = 'chicken'
    DUCK = 'duck'
    TURKEY = 'turkey'
    CARABAO = 'carabao'
    RABBIT = 'rabbit'
    FISH = 'fish'
    OTHER = 'other'


class RecordType(Enum):
    """Health record type enumeration"""
    VACCINE = 'vaccine'
    VITAMIN = 'vitamin'
    MEDICATION = 'medication'
    CHECKUP = 'checkup'
    TREATMENT = 'treatment'
    DEWORMING = 'deworming'


class Livestock(db.Model):
    """Livestock model for storing animal information"""
    __tablename__ = 'livestock'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    farm = db.relationship('Farm', backref=db.backref('livestock', lazy=True, cascade='all, delete-orphan'))
    
    # Animal identification
    animal_type = db.Column(db.String(50), nullable=False)  # cattle, pig, chicken, etc.
    breed = db.Column(db.String(100))
    unique_id = db.Column(db.String(100), unique=True)  # Tag number, ear mark, etc.
    name = db.Column(db.String(120))  # Optional name
    
    # Demographics
    age_months = db.Column(db.Integer)  # Age in months
    birth_date = db.Column(db.DateTime)
    gender = db.Column(db.String(20))  # Male, Female, or Unknown
    weight_kg = db.Column(db.Float)  # Weight in kilograms
    
    # Count for herd animals
    count = db.Column(db.Integer, default=1)  # For groups of animals (flock of chickens, etc.)
    
    # Status
    status = db.Column(db.String(50), default='active')  # active, sold, deceased, transferred
    status_date = db.Column(db.DateTime)  # Date status changed
    
    # Acquisition
    acquisition_date = db.Column(db.DateTime, nullable=False)
    acquisition_cost = db.Column(db.Float)
    source = db.Column(db.String(200))  # Where the animal came from
    
    # Location
    location_description = db.Column(db.String(200))  # Barn, pen, pasture, etc.
    
    # Notes
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    nutrition_records = db.relationship('NutritionRecord', backref='livestock', lazy=True, cascade='all, delete-orphan')
    health_records = db.relationship('HealthRecord', backref='livestock', lazy=True, cascade='all, delete-orphan')
    productivity_records = db.relationship('ProductivityRecord', backref='livestock', lazy=True, cascade='all, delete-orphan')
    events = db.relationship('LivestockEvent', backref='livestock', lazy=True, cascade='all, delete-orphan', order_by='LivestockEvent.event_date.desc()')
    weight_logs = db.relationship('LivestockWeightLog', backref='livestock', lazy=True, cascade='all, delete-orphan', order_by='LivestockWeightLog.weighed_at.desc()')
    
    # Indexes
    __table_args__ = (
        db.Index('ix_livestock_farm_id', 'farm_id'),
        db.Index('ix_livestock_animal_type', 'animal_type'),
        db.Index('ix_livestock_status', 'status'),
        db.Index('ix_livestock_unique_id', 'unique_id'),
    )
    
    def __repr__(self):
        return f'<Livestock {self.animal_type} {self.unique_id}>'
    
    def get_age_display(self):
        """Get formatted age"""
        if self.age_months:
            years = self.age_months // 12
            months = self.age_months % 12
            if years > 0 and months > 0:
                return f"{years}y {months}m"
            elif years > 0:
                return f"{years}y"
            else:
                return f"{months}m"
        return "Unknown"
    
    def get_next_vaccine(self):
        """Get next scheduled vaccine"""
        from app.models.livestock import HealthRecord
        next_vaccine = HealthRecord.query.filter(
            HealthRecord.livestock_id == self.id,
            HealthRecord.record_type == 'vaccine',
            HealthRecord.next_due_date != None,
            HealthRecord.next_due_date > datetime.utcnow()
        ).order_by(HealthRecord.next_due_date).first()
        return next_vaccine

    # Market-readiness thresholds per animal type
    READY_THRESHOLDS = {
        'cattle':   {'min_age_months': 18, 'min_weight_kg': 300},
        'carabao':  {'min_age_months': 18, 'min_weight_kg': 300},
        'pig':      {'min_age_months': 5,  'min_weight_kg': 80},
        'goat':     {'min_age_months': 8,  'min_weight_kg': 20},
        'chicken':  {'min_age_months': 3,  'min_weight_kg': None},
        'duck':     {'min_age_months': 3,  'min_weight_kg': None},
        'turkey':   {'min_age_months': 4,  'min_weight_kg': None},
        'rabbit':   {'min_age_months': 3,  'min_weight_kg': 1.5},
        'fish':     {'min_age_months': 4,  'min_weight_kg': None},
        'other':    {'min_age_months': 6,  'min_weight_kg': None},
    }

    @property
    def is_ready_for_sale(self):
        """Return True if animal meets market-readiness thresholds"""
        if self.status != 'active':
            return False
        thresholds = self.READY_THRESHOLDS.get(self.animal_type, {'min_age_months': 6, 'min_weight_kg': None})
        min_age = thresholds['min_age_months']
        min_weight = thresholds['min_weight_kg']
        age_ok = (self.age_months or 0) >= min_age
        weight_ok = (min_weight is None) or ((self.weight_kg or 0) >= min_weight)
        return age_ok and weight_ok

    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'farm_id': self.farm_id,
            'animal_type': self.animal_type,
            'breed': self.breed,
            'unique_id': self.unique_id,
            'name': self.name,
            'age_months': self.age_months,
            'birth_date': self.birth_date.isoformat() if self.birth_date else None,
            'gender': self.gender,
            'weight_kg': self.weight_kg,
            'count': self.count,
            'status': self.status,
            'acquisition_date': self.acquisition_date.isoformat() if self.acquisition_date else None,
            'acquisition_cost': self.acquisition_cost,
            'location_description': self.location_description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class NutritionRecord(db.Model):
    """Nutrition and feeding records"""
    __tablename__ = 'nutrition_records'
    
    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)
    
    # Food information
    food_type = db.Column(db.String(100), nullable=False)  # pellet feed, corn, grass, swill, etc.
    description = db.Column(db.String(200))
    quantity_kg = db.Column(db.Float, nullable=False)  # Quantity in kg
    quantity_unit = db.Column(db.String(50), default='kg')  # kg, liters, pcs, etc.
    
    # Feeding schedule
    feeding_frequency = db.Column(db.String(100))  # daily, 2x daily, weekly, etc.
    feeding_time = db.Column(db.String(100))  # morning, afternoon, etc.
    
    # Cost
    cost_per_unit = db.Column(db.Float)
    total_cost = db.Column(db.Float)
    
    # Supplier
    supplier_name = db.Column(db.String(200))
    supplier_contact = db.Column(db.String(200))
    
    # Dates
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    last_restocked = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Notes
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_nutrition_livestock_id', 'livestock_id'),
        db.Index('ix_nutrition_is_active', 'is_active'),
    )
    
    def __repr__(self):
        return f'<NutritionRecord {self.food_type}>'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'livestock_id': self.livestock_id,
            'food_type': self.food_type,
            'description': self.description,
            'quantity_kg': self.quantity_kg,
            'feeding_frequency': self.feeding_frequency,
            'cost_per_unit': self.cost_per_unit,
            'supplier_name': self.supplier_name,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class HealthRecord(db.Model):
    """Health, vaccine, and medical records"""
    __tablename__ = 'health_records'
    
    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)
    vaccine_inventory_id = db.Column(db.Integer, db.ForeignKey('vaccine_inventory.id'), nullable=True)  # Link to vaccine inventory
    
    # Relationship to VaccineInventory
    vaccine_inventory = db.relationship('VaccineInventory', backref=db.backref('health_records', lazy=True))
    
    # Record type
    record_type = db.Column(db.String(50), nullable=False)  # vaccine, vitamin, medication, checkup, etc.
    
    # Details
    name = db.Column(db.String(200), nullable=False)  # e.g., "FMD Vaccine", "Vitamin A"
    description = db.Column(db.Text)
    dosage = db.Column(db.String(100))
    
    # Dates
    date_administered = db.Column(db.DateTime, nullable=False)
    next_due_date = db.Column(db.DateTime)  # When the next dose is due
    
    # Provider
    veterinarian_name = db.Column(db.String(200))
    clinic_name = db.Column(db.String(200))
    contact_info = db.Column(db.String(200))
    
    # Cost
    cost = db.Column(db.Float)
    
    # Result/Status
    result = db.Column(db.String(200))  # passed, failed, pending, etc.
    status = db.Column(db.String(50), default='completed')  # completed, pending, overdue
    
    # Notes
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_health_livestock_id', 'livestock_id'),
        db.Index('ix_health_record_type', 'record_type'),
        db.Index('ix_health_status', 'status'),
    )
    
    def __repr__(self):
        return f'<HealthRecord {self.name}>'
    
    def is_overdue(self):
        """Check if record is overdue"""
        if self.next_due_date and self.next_due_date < datetime.utcnow():
            return True
        return False
    
    def days_until_due(self):
        """Get days until due"""
        if self.next_due_date:
            delta = self.next_due_date - datetime.utcnow()
            return delta.days
        return None
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'livestock_id': self.livestock_id,
            'record_type': self.record_type,
            'name': self.name,
            'description': self.description,
            'date_administered': self.date_administered.isoformat() if self.date_administered else None,
            'next_due_date': self.next_due_date.isoformat() if self.next_due_date else None,
            'veterinarian_name': self.veterinarian_name,
            'cost': self.cost,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProductivityRecord(db.Model):
    """Production and productivity tracking"""
    __tablename__ = 'productivity_records'
    
    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)
    
    # Metric type
    metric_type = db.Column(db.String(100), nullable=False)  # eggs_laid, milk_produced, weight_gain, offspring, etc.
    
    # Value
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)  # pcs, liters, kg, etc.
    
    # Date
    record_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Value/Income
    market_value = db.Column(db.Float)  # How much it sold for
    
    # Notes
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_productivity_livestock_id', 'livestock_id'),
        db.Index('ix_productivity_metric_type', 'metric_type'),
        db.Index('ix_productivity_record_date', 'record_date'),
    )
    
    def __repr__(self):
        return f'<ProductivityRecord {self.metric_type}>'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'livestock_id': self.livestock_id,
            'metric_type': self.metric_type,
            'quantity': self.quantity,
            'unit': self.unit,
            'record_date': self.record_date.isoformat() if self.record_date else None,
            'market_value': self.market_value,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class LivestockEvent(db.Model):
    """Death, sale, and transfer events for livestock"""
    __tablename__ = 'livestock_events'

    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)

    # Event type: death | sale | transfer
    event_type = db.Column(db.String(20), nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)

    # How many heads affected (for batch records)
    count_affected = db.Column(db.Integer, nullable=False, default=1)

    # Death-specific
    cause_of_death = db.Column(db.String(100))  # disease, accident, natural, culled

    # Sale-specific
    buyer_name = db.Column(db.String(200))
    buyer_contact = db.Column(db.String(200))
    price_per_head = db.Column(db.Float)
    total_revenue = db.Column(db.Float)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_livestock_events_livestock_id', 'livestock_id'),
    )

    def __repr__(self):
        return f'<LivestockEvent {self.event_type} x{self.count_affected}>'


class LivestockWeightLog(db.Model):
    """Weight history snapshots for livestock"""
    __tablename__ = 'livestock_weight_logs'

    id = db.Column(db.Integer, primary_key=True)
    livestock_id = db.Column(db.Integer, db.ForeignKey('livestock.id'), nullable=False)

    weight_kg = db.Column(db.Float, nullable=False)
    weighed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_weight_log_livestock_id', 'livestock_id'),
    )

    def __repr__(self):
        return f'<LivestockWeightLog {self.weight_kg}kg>'
