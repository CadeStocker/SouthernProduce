import datetime
from io import BytesIO
from sqlite3 import IntegrityError
import traceback
from flask_mailman import EmailMessage
import json
import math
from fpdf import FPDF
import matplotlib
from producepricer.blueprints import ai, api, auth, company, customers, email_templates, items, packaging, pricing, raw_products, receiving
from producepricer.utils.matching import best_match
from producepricer.auth_utils import require_api_key, optional_api_key_or_login, get_api_key_from_request, validate_api_key
from producepricer.utils.parsing import coerce_iso_date, parse_price_list_with_openai
from producepricer.utils.price_sheet_utils import create_price_sheet_backup
matplotlib.use('Agg')  # Use 'Agg' backend for rendering without a display
import matplotlib.pyplot as plt
from flask import (
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
    flash,
    make_response,
    Blueprint,
    current_app,
    send_from_directory
)
from itsdangerous import BadSignature, Serializer, SignatureExpired
from producepricer.models import (
    AIResponse,
    APIKey,
    BrandName,
    CostHistory, 
    Customer,
    CustomerEmail,
    DesignationCost,
    EmailTemplate,
    GrowerOrDistributor,
    Item,
    ItemDesignation, 
    ItemInfo, 
    ItemTotalCost, 
    LaborCost, 
    PackagingCost,
    PriceHistory,
    PriceSheet, 
    RanchPrice, 
    RawProduct,
    ReceivingImage,
    ReceivingLog,
    Seller,
    UnitOfWeight, 
    User, 
    Company, 
    Packaging,
    PendingUser
)
from producepricer.forms import(
    AddBrandName,
    AddCustomer,
    AddCustomerEmail,
    AddDesignationCost,
    AddGrowerOrDistributor,
    AddItem, 
    AddLaborCost, 
    AddPackagingCost, 
    AddRanchPrice, 
    AddRawProduct, 
    AddRawProductCost,
    AddSeller,
    CreatePackage,
    DeleteForm, 
    EditItem,
    EditRawProduct,
    EmailTemplateForm,
    PriceQuoterForm,
    PriceSheetForm, 
    ResetPasswordForm, 
    ResetPasswordRequestForm, 
    SignUp, 
    Login, 
    CreateCompany, 
    UpdateItemInfo,
    UploadCSV, 
    UploadCustomerCSV, 
    UploadItemCSV, 
    UploadPackagingCSV, 
    UploadRawProductCSV
)
from flask_login import login_user, login_required, current_user, logout_user
from producepricer import db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_mailman import EmailMessage
from producepricer.utils.ai_utils import get_ai_response
from producepricer.utils.qr_utils import generate_api_key_qr_code, generate_qr_code_bytes
import pdfplumber
import tempfile
from sqlalchemy import func

# Use the shared Blueprint instance so all blueprint sub-modules and routes.py
# register on the same object that gets registered with the Flask app.
from producepricer.blueprints._blueprint import main

# function to extract text from PDF - moved to utils/pdf_utils.py to avoid circular imports
from producepricer.utils.pdf_utils import extract_pdf_text  # noqa: F401 (re-exported for backwards compat)

# route for the root URL
@main.route('/')
@main.route('/home')
@login_required
def home():
    return render_template('home.html')

# about page
@main.route('/about')
def about():
    return render_template('about.html')


def safe_strip(x):
    if x is None: return ''
    try:
        if math.isnan(x): return ''
    except Exception:
        pass
    return str(x).strip()

# only true if this file is run directly
if __name__ == '__main__':
    current_app.run(debug=True)