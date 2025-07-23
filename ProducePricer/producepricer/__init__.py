import os
from flask import Flask
from flask_mailman import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

# Initialize extensions outside create_app
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
mail = Mail()
csrf = CSRFProtect()

def create_app(db_uri=None):
    # Initialize Flask app
    app = Flask(__name__)

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
    with app.app_context():
        from producepricer import routes
        app.register_blueprint(routes.main)

    return app

# Create the application instance
app = create_app()