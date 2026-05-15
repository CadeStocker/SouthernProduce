# Copyright Cade Stocker 2026
import os
from flask import Flask
try:
    from flask_mail import Mail
except ImportError:
    Mail = None  # Handle the case where flask_mail is not installed
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate, migrate
from flask_wtf import CSRFProtect
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize extensions outside create_app
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
mail = Mail() if Mail else None
csrf = CSRFProtect()
migrate = Migrate()

# Initialize OpenAI client (lazy-loaded to handle missing API key)
openai_client = None

def get_openai_client():
    """Get or create OpenAI client. Handles missing API key gracefully."""
    global openai_client
    if openai_client is None:
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            openai_client = OpenAI(api_key=api_key)
        else:
            # Return a dummy client that will fail when used
            # This allows the app to start without the API key
            return None
    return openai_client

def create_app(db_uri=None):
    # Initialize Flask app
    app = Flask(__name__)
    
    # turn back off
    app.config['DEBUG'] = True

    # --- START: Production Database Configuration ---
    # This logic checks if it's running on Render by looking for the mounted disk.
    render_data_dir = '/var/data'
    db_path = os.path.join(render_data_dir, 'site.db')

    # Check if the Render data directory exists
    if os.path.exists(render_data_dir):
        # If on Render, use the persistent disk path
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        # Use persistent disk for images, outside of static folder
        app.config['RECEIVING_IMAGES_DIR'] = os.path.join(render_data_dir, 'receiving_images')
    else:
        # Otherwise, use the local instance folder for development
        local_db_path = os.path.join(app.instance_path, 'site.db')
        os.makedirs(app.instance_path, exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{local_db_path}'
        # Use instance folder for local development images
        app.config['RECEIVING_IMAGES_DIR'] = os.path.join(app.instance_path, 'receiving_images')
    
    # Ensure the image directory exists
    os.makedirs(app.config['RECEIVING_IMAGES_DIR'], exist_ok=True)
    # --- END: Production Database Configuration ---

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey')
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
    app.config['NOTIFICATION_OUTLIER_PERCENT_THRESHOLD'] = float(
        os.environ.get('NOTIFICATION_OUTLIER_PERCENT_THRESHOLD', '10')
    )
    app.config['NOTIFICATION_PRICE_CHANGE_PERCENT_THRESHOLD'] = float(
        os.environ.get('NOTIFICATION_PRICE_CHANGE_PERCENT_THRESHOLD', '20')
    )
    
    # Set database URI - use parameter if provided (for testing)
    if db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    # else:
    #     app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # attempt to fix "No such command 'db'" error
    migrate.init_app(app, db)
    # Set up database migration
    #migrate = Migrate(app, db)

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Configure email settings
    app.config.update(
        MAIL_SERVER   = 'smtp.gmail.com',
        MAIL_PORT     = 465,
        MAIL_USE_SSL  = True,
        MAIL_USERNAME = os.environ.get('EMAIL_USER'),
        MAIL_PASSWORD = os.environ.get('EMAIL_PASS'),
        MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_USER'),
    )
    app.config['RESET_PASS_TOKEN_MAX_AGE'] = 3600  # 1 hour
    
    # Initialize Flask-Mail or Flask-Mailman
    try:
        from flask_mailman import Mail
        MAILMAN_PREFERRED = True
    except Exception:
        Mail = None
        MAILMAN_PREFERRED = False

    # Use Flask-Mailman if available, otherwise fallback to Flask-Mail
    mail = Mail() if Mail else None

    # Initialize mail with app if mail is available
    if mail:
        mail.init_app(app)
    else:
        app.logger.warning("Warning: flask_mail is not installed. Email functionality will be disabled.")


    # Import and register blueprints
    # Important: Do this INSIDE create_app to avoid circular imports
    from app.routes import main
    from app.api import api
    
    # Exempt API from CSRF protection as it will be used by external clients (iPad app)
    csrf.exempt(api)
    
    app.register_blueprint(main)
    app.register_blueprint(api)

    # Import all sub-modules to register routes on `main`
    from app.blueprints import auth, ai, raw_products, packaging, items, receiving, pricing, customers, company, email_templates, inventory
    
    # Add custom Jinja2 filter to convert newlines to <br> tags
    @app.template_filter('nl2br')
    def nl2br_filter(text):
        """Convert newlines to HTML <br> tags for email templates"""
        if not text:
            return text
        # Replace \r\n, \r, and \n with <br> tags
        from markupsafe import Markup
        text = text.replace('\r\n', '<br>').replace('\r', '<br>').replace('\n', '<br>')
        return Markup(text)
    
    # Commented out until we create the AI routes
    # from app.routes.ai import ai_bp
    # app.register_blueprint(ai_bp, url_prefix='/ai')

    return app

# Create the application instance
#app = create_app()