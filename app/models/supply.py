from app import db
from datetime import datetime

class Supply(db.Model):
    __tablename__ = 'supplies'
    
    id = db.Column(db.Integer, primary_key=True)
    supply_type = db.Column(db.String(50), nullable=False)  # vaccine, feed, fertilizer, seeds
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    unit = db.Column(db.String(20), nullable=False)  # doses, kg, bottles, packets
    unit_cost = db.Column(db.Float)  # Cost per unit
    reorder_level = db.Column(db.Float, default=10)  # Alert when stock falls below this
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    inventory_levels = db.relationship('SupplyInventory', lazy=True, cascade='all, delete-orphan')
    distributions = db.relationship('SupplyDistribution', lazy=True, cascade='all, delete-orphan')
    usage_records = db.relationship('SupplyUsageRecord', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Supply {self.name} ({self.supply_type})>'
    
    def total_available(self):
        """Get total available quantity across all inventory"""
        return sum([inv.quantity_available for inv in self.inventory_levels])
    
    def is_low_stock(self):
        """Check if any inventory location is below reorder level"""
        return any(inv.quantity_available < self.reorder_level for inv in self.inventory_levels)


class SupplyInventory(db.Model):
    __tablename__ = 'supply_inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    quantity_available = db.Column(db.Float, default=0)
    quantity_reserved = db.Column(db.Float, default=0)  # Reserved for pending distributions
    warehouse_location = db.Column(db.String(100))  # Storage location
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<SupplyInventory {self.supply.name} - {self.quantity_available} {self.supply.unit}>'
    
    def quantity_available_for_distribution(self):
        """Get quantity that can be distributed (available - reserved)"""
        return self.quantity_available - self.quantity_reserved


class SupplyDistribution(db.Model):
    __tablename__ = 'supply_distributions'
    
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    distributed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Staff member
    quantity = db.Column(db.Float, nullable=False)
    distribution_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='distributed')  # distributed, returned, lost
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    supply = db.relationship('Supply', overlaps='distributions')
    farm = db.relationship('Farm', backref=db.backref('supply_distributions', lazy=True))
    staff_member = db.relationship('User', backref=db.backref('supply_distributions', lazy=True))
    
    def __repr__(self):
        return f'<SupplyDistribution {self.supply.name} to {self.farm.name}>'


class SupplyUsageRecord(db.Model):
    __tablename__ = 'supply_usage_records'
    
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    record_type = db.Column(db.String(50), nullable=False)  # livestock_vaccination, crop_fertilization, animal_feed, etc.
    related_id = db.Column(db.Integer)  # ID of the related entity (livestock ID, crop ID, etc.)
    quantity_used = db.Column(db.Float, nullable=False)
    usage_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # User who recorded it
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    supply = db.relationship('Supply', overlaps='usage_records')
    farm = db.relationship('Farm', backref=db.backref('supply_usage_records', lazy=True))
    user = db.relationship('User', backref=db.backref('supply_usage_records', lazy=True))
    
    def __repr__(self):
        return f'<SupplyUsageRecord {self.supply.name} - {self.quantity_used} {self.supply.unit}>'


class FarmSupplyInventory(db.Model):
    """Tracks inventory items owned by individual farms (municipality-received or self-purchased)"""
    __tablename__ = 'farm_supply_inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    item_name = db.Column(db.String(150), nullable=False)  # Custom name (e.g., "Coco Fertilizer", "Layer Feed")
    item_type = db.Column(db.String(50), nullable=False)  # fertilizer, feed, seeds, pesticide, etc.
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)  # kg, bags, liters, packets, etc.
    source = db.Column(db.String(50), nullable=False)  # 'municipality' or 'farmer_purchased'
    purchase_date = db.Column(db.Date)  # When acquired
    unit_cost = db.Column(db.Float)  # Optional: cost per unit
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_farm_supply_inventory_farm_id', 'farm_id'),
        db.Index('ix_farm_supply_inventory_source', 'source'),
    )
    
    # Relationships
    farm = db.relationship('Farm', backref=db.backref('supply_inventory_items', lazy=True, cascade='all, delete-orphan'))
    usage_history = db.relationship('FarmSupplyUsage', lazy=True, cascade='all, delete-orphan', overlaps='direct_usage_history,farm_supply')
    
    def __repr__(self):
        return f'<FarmSupplyInventory {self.item_name} - {self.quantity} {self.unit}>'
    
    def total_used(self):
        """Get total quantity used from this inventory"""
        return sum(u.quantity_used for u in self.usage_history)
    
    def quantity_remaining(self):
        """Get remaining quantity after usage"""
        return self.quantity - self.total_used()


class FarmSupplyUsage(db.Model):
    """Track when and how farm inventory items are used"""
    __tablename__ = 'farm_supply_usage'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_supply_id = db.Column(db.Integer, db.ForeignKey('farm_supply_inventory.id'), nullable=False)
    usage_type = db.Column(db.String(50), nullable=False)  # 'livestock_health', 'livestock_feeding', 'crop_application', etc.
    related_model = db.Column(db.String(50))  # 'livestock', 'crop', 'farm', etc.
    related_id = db.Column(db.Integer)  # ID of livestock/crop being treated
    quantity_used = db.Column(db.Float, nullable=False)
    usage_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    farm_supply = db.relationship('FarmSupplyInventory', backref=db.backref('direct_usage_history', lazy=True), overlaps='usage_history')
    recorded_by = db.relationship('User', backref=db.backref('farm_supply_usages', lazy=True))
    
    def __repr__(self):
        return f'<FarmSupplyUsage {self.quantity_used} used on {self.usage_date}>'
