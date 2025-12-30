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

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

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
        from producepricer.models import User
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
    from producepricer.routes import main
    from producepricer.api import api
    
    # Exempt API from CSRF protection as it will be used by external clients (iPad app)
    csrf.exempt(api)
    
    app.register_blueprint(main)
    app.register_blueprint(api)
    
    # Commented out until we create the AI routes
    # from producepricer.routes.ai import ai_bp
    # app.register_blueprint(ai_bp, url_prefix='/ai')

    return app

# Create the application instance
#app = create_app()