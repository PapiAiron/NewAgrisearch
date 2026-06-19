"""
Farm model
"""
from app import db
from datetime import datetime

class Farm(db.Model):
    """Farm model for storing farm information"""
    __tablename__ = 'farms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    crop_type = db.Column(db.String(100), nullable=False)
    area_square_meters = db.Column(db.Float, nullable=False)
    
    # Location
    barangay_id = db.Column(db.Integer, nullable=False)
    barangay_name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    lot_boundary_geojson = db.Column(db.Text)
    
    # Owner information
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    owner = db.relationship('User', backref=db.backref('farms', lazy=True, cascade='all, delete-orphan'))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        db.Index('ix_farms_owner_id', 'owner_id'),
        db.Index('ix_farms_barangay_id', 'barangay_id'),
        db.Index('ix_farms_is_active', 'is_active'),
    )
    
    def __repr__(self):
        return f'<Farm {self.name}>'
    
    def to_dict(self):
        """Convert farm to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'crop_type': self.crop_type,
            'area_square_meters': self.area_square_meters,
            'barangay_id': self.barangay_id,
            'barangay_name': self.barangay_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'lot_boundary_geojson': self.lot_boundary_geojson,
            'owner_id': self.owner_id,
            'owner_name': self.owner.full_name if self.owner else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
