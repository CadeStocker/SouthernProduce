from flask_wtf import FlaskForm
from wtforms import DateField, FileField, FloatField, SelectField, SelectMultipleField, StringField, PasswordField, SubmitField, BooleanField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length
from producepricer.models import UnitOfWeight, User, Company

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

# package is separate from it's prices
class CreatePackage(FlaskForm):
    name = StringField('Package Name', validators=[DataRequired()])
    submit = SubmitField('Create Package')

class AddPackagingCost(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    box_cost = FloatField('Box Cost', validators=[DataRequired()])
    bag_cost = FloatField('Bag Cost', validators=[DataRequired()])
    tray_andor_chemical_cost = FloatField('Tray and/or Chemical Cost', validators=[DataRequired()])
    label_andor_tape_cost = FloatField('Label and/or Tape Cost', validators=[DataRequired()])
    submit = SubmitField('Add Packaging Cost')

# allow import of csv file for packaging costs
class UploadPackagingCSV(FlaskForm):
    file = FileField('Upload CSV', validators=[DataRequired()])
    submit = SubmitField('Upload')

# create new raw product
class AddRawProduct(FlaskForm):
    name = StringField('Raw Product Name', validators=[DataRequired()])
    submit = SubmitField('Add Raw Product')

# raw product cost
class AddRawProductCost(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    cost = FloatField('Cost', validators=[DataRequired()])
    submit = SubmitField('Add Raw Product Cost')

class UploadRawProductCSV(FlaskForm):
    file = FileField('Upload CSV', validators=[DataRequired()])
    submit = SubmitField('Upload')

class AddItem(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    item_code = StringField('Item Code', validators=[DataRequired()])
    unit_of_weight = SelectField('Unit of Weight', choices=[(choice.name, choice.value) for choice in UnitOfWeight], validators=[DataRequired()])
    #weight = FloatField('Weight', validators=[DataRequired()])
    packaging = SelectField('Packaging', coerce=int, validators=[DataRequired()])
    raw_products = SelectMultipleField('Raw Products', coerce=int, validators=[DataRequired()])
    ranch = BooleanField('Ranch', default=False)
    case_weight = FloatField('Case Weight', default=0.0)
    item_designation = SelectField('Item Designation', choices=[('SNAKPAK', 'SnakPak'), ('RETAIL', 'Retail'), ('FOODSERVICE', 'Food Service')], validators=[DataRequired()])
    submit = SubmitField('Add Item')

class UploadItemCSV(FlaskForm):
    file = FileField('Upload CSV', validators=[DataRequired()])
    submit = SubmitField('Upload')