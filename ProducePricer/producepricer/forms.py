from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, PasswordField, SubmitField, BooleanField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length
from producepricer.models import User, Company

class SignUp(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password',
                                      validators=[DataRequired(), EqualTo('password')])
    remember = BooleanField('Remember Me')
    company = SelectField('Company', validators=[DataRequired()])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')
        
    def validate_password(self, password):
        if len(password.data) < 6:
            raise ValidationError('Password must be at least 6 characters long.')
        if not any(char.isdigit() for char in password.data):
            raise ValidationError('Password must contain at least one digit.')
        if not any(char.isalpha() for char in password.data):
            raise ValidationError('Password must contain at least one letter.')

class Login(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class CreateCompany(FlaskForm):
    name = StringField('Company Name', validators=[DataRequired()])
    admin_email = StringField('Admin Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Create Company')

    def validate_name(self, name):
        company = Company.query.filter_by(name=name.data).first()
        if company:
            raise ValidationError('That company name is already in use. Please choose a different one.')

