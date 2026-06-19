from app import db
from datetime import datetime

class Crop(db.Model):
    __tablename__ = 'crops'
    
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farms.id'), nullable=False)
    crop_type = db.Column(db.String(100), nullable=False)  # rice, corn, vegetables, etc.
    planting_date = db.Column(db.Date, nullable=False)
    current_growth_stage = db.Column(db.String(50), default='seedling')  # seedling, vegetative, flowering, fruiting, mature
    expected_harvest_date = db.Column(db.Date)
    yield_amount = db.Column(db.Float)
    yield_unit = db.Column(db.String(20), default='kg')  # kg, bags, tons
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')  # active, harvested, failed, abandoned
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    farm = db.relationship('Farm', backref=db.backref('crops', lazy=True))
    growth_records = db.relationship('CropGrowthRecord', backref='crop', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Crop {self.crop_type} - {self.farm.name}>'
    
    def days_since_planting(self):
        from datetime import date
        return (date.today() - self.planting_date).days
    
    def days_to_harvest(self):
        from datetime import date
        if self.expected_harvest_date:
            return (self.expected_harvest_date - date.today()).days
        return None


class CropGrowthRecord(db.Model):
    __tablename__ = 'crop_growth_records'
    
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crops.id'), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    growth_stage = db.Column(db.String(50))  # Current growth stage at record date
    height_cm = db.Column(db.Float)  # Height in cm
    health_status = db.Column(db.String(20), default='healthy')  # healthy, stressed, diseased
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CropGrowthRecord Crop {self.crop_id} - {self.record_date}>'
