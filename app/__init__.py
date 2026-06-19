from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import config
import os

db = SQLAlchemy()

def create_app(config_name=None):
    """Application factory function"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), 'static'))
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Import models to ensure they're registered with SQLAlchemy
    from app.models.user import User, PasswordReset
    from app.models.farm import Farm
    from app.models.livestock import Livestock, NutritionRecord, HealthRecord, ProductivityRecord, LivestockEvent, LivestockWeightLog
    from app.models.health import VaccineInventory, DiseaseRecord, HealthAlert
    from app.models.crop import Crop, CropGrowthRecord
    from app.models.supply import Supply, SupplyInventory, SupplyDistribution, SupplyUsageRecord, FarmSupplyInventory, FarmSupplyUsage
    from app.models.distribution import DistributionRequest, DistributionEvent, DistributionRecord
    from app.models.chat import ChatConversation, ChatMessage

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.farm import farm_bp
    from app.routes.livestock import livestock_bp
    from app.routes.health import health_bp
    from app.routes.crop import crop_bp
    from app.routes.supply import supply_bp
    from app.routes.distribution import distribution_bp
    from app.routes.chatbot import chatbot_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(farm_bp, url_prefix='/farm')
    app.register_blueprint(livestock_bp, url_prefix='/livestock')
    app.register_blueprint(health_bp, url_prefix='/health')
    app.register_blueprint(crop_bp, url_prefix='/crop')
    app.register_blueprint(supply_bp, url_prefix='/supply')
    app.register_blueprint(distribution_bp, url_prefix='/distribution')
    app.register_blueprint(chatbot_bp, url_prefix='/chatbot')
    
    # Session management - mark all authenticated sessions as permanent
    @app.before_request
    def make_session_permanent():
        from flask import session
        if 'user_id' in session:
            session.permanent = True  # Apply PERMANENT_SESSION_LIFETIME
    
    # Root route - redirect based on login status
    @app.route('/')
    def index():
        from flask import redirect, render_template, session
        if 'user_id' in session:
            return redirect('/dashboard/')
        return render_template('landing.html')
    
    # Context processor to inject user data into templates (with error handling)
    @app.context_processor
    def inject_user():
        from flask import session
        user_data = {}
        try:
            if 'user_id' in session:
                user = User.query.get(session['user_id'])
                if user:
                    user_data = {
                        'user': user,
                        'user_email': user.email,
                        'user_barangay': user.barangay_name,
                        'user_active': user.is_active,
                        'user_verified': user.is_verified
                    }
        except Exception as e:
            logger = __import__('logging').getLogger(__name__)
            logger.error(f"Error in inject_user context processor: {str(e)}")
            # Continue without user data rather than crashing
        return user_data
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return {'error': 'Internal server error'}, 500
    
    # Create tables with app context
    with app.app_context():
        db.create_all()
    
    return app
