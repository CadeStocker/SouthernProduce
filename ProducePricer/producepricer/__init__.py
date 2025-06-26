import os
from flask import Flask
from flask_mailman import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

# Initialize Flask app and extensions
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = '33d151aee312625a351143d17aeb358f'

# define the upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# define the allowed extensions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

# database setup
db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)

# login manager setup
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# CSRF protection
csrf = CSRFProtect(app)

# mail settings
app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 465
app.config['MAIL_USE_SSL']  = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
app.config['RESET_PASS_TOKEN_MAX_AGE'] = 3600  # 1 hour

mail = Mail(app)

from producepricer import routes