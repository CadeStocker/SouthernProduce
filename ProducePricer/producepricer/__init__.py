import os
from flask import Flask
from flask_mailman import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
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
mail = Mail()
csrf = CSRFProtect()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

def create_app(db_uri=None):
    # Initialize Flask app
    app = Flask(__name__)

    # --- START: Production Database Configuration ---
    # This logic checks if it's running on Render by looking for the mounted disk.
    render_data_dir = '/var/data'
    db_path = os.path.join(render_data_dir, 'site.db')

    if os.path.exists(render_data_dir):
        # If on Render, use the persistent disk path
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    else:
        # Otherwise, use the local instance folder for development
        local_db_path = os.path.join(app.instance_path, 'site.db')
        os.makedirs(app.instance_path, exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{local_db_path}'
    # --- END: Production Database Configuration ---

    # Configuration
    app.config['SECRET_KEY'] = '33d151aee312625a351143d17aeb358f'
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
    
    # Set database URI - use parameter if provided (for testing)
    if db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Set up database migration
    migrate = Migrate(app, db)
    
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
    mail.init_app(app)

    # Import and register blueprints
    # Important: Do this INSIDE create_app to avoid circular imports
    from producepricer.routes import main
    app.register_blueprint(main)
    
    # Commented out until we create the AI routes
    # from producepricer.routes.ai import ai_bp
    # app.register_blueprint(ai_bp, url_prefix='/ai')

    return app

# Create the application instance
#app = create_app()