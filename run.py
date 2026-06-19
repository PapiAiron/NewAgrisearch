#!/usr/bin/env python
"""
Application entry point
"""
import os
from app import create_app, db
from app.models.user import User, PasswordReset
from app.models.farm import Farm
from app.models.crop import Crop, CropGrowthRecord
from app.models.supply import Supply, SupplyInventory, SupplyDistribution, SupplyUsageRecord
from db_init import create_database_if_not_exists

# Create database if it doesn't exist
create_database_if_not_exists()

app = create_app(os.getenv('FLASK_ENV', 'development'))

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'PasswordReset': PasswordReset,
        'Farm': Farm,
        'Crop': Crop,
        'CropGrowthRecord': CropGrowthRecord,
        'Supply': Supply,
        'SupplyInventory': SupplyInventory,
        'SupplyDistribution': SupplyDistribution,
        'SupplyUsageRecord': SupplyUsageRecord
    }

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.getenv('API_PORT', 5000))
    # Enable debug mode if FLASK_ENV=development
    debug_mode = os.getenv('FLASK_ENV', 'development') == 'development'
    # To enable HTTPS (required for GPS on mobile), change ssl_context=None to ssl_context='adhoc'
    ssl = os.getenv('FLASK_HTTPS', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False,
            ssl_context='adhoc' if ssl else None)
