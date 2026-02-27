from flask_mailman import EmailMessage
from producepricer.blueprints._blueprint import main

from flask import (
    redirect,
    render_template,
    url_for,
    flash,
    current_app
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

@main.route('/email_templates', methods=['GET', 'POST'])
@login_required
def email_templates():
    """List and create email templates for the current company."""
    form = EmailTemplateForm()
    delete_form = DeleteForm()
    # Handle creation
    if form.validate_on_submit():
        # if the new template is marked default, unset other defaults
        if form.is_default.data:
            EmailTemplate.query.filter_by(company_id=current_user.company_id, is_default=True).update({'is_default': False})
        tpl = EmailTemplate(
            name=form.name.data,
            subject=form.subject.data,
            body=form.body.data,
            company_id=current_user.company_id,
            is_default=bool(form.is_default.data)
        )
        db.session.add(tpl)
        db.session.commit()
        flash('Email template saved.', 'success')
        return redirect(url_for('main.email_templates'))

    # get existing templates
    templates = EmailTemplate.query.filter_by(company_id=current_user.company_id).order_by(EmailTemplate.is_default.desc(), EmailTemplate.name.asc()).all()
    return render_template('email_templates.html', title='Email Templates', templates=templates, form=form, delete_form=delete_form)


@main.route('/email_template/<int:template_id>/edit', methods=['GET','POST'])
@login_required
def edit_email_template(template_id):
    # get desired template
    tpl = EmailTemplate.query.filter_by(id=template_id, company_id=current_user.company_id).first_or_404()
    # use the same form, but to edit instead of create
    form = EmailTemplateForm(obj=tpl)
    if form.validate_on_submit():
        # if you make it the default, take away default status from existing template
        if form.is_default.data:
            EmailTemplate.query.filter_by(company_id=current_user.company_id, is_default=True).update({'is_default': False})
        tpl.name = form.name.data
        tpl.subject = form.subject.data
        tpl.body = form.body.data
        tpl.is_default = bool(form.is_default.data)
        db.session.commit()
        flash('Template updated.', 'success')
        return redirect(url_for('main.email_templates'))
    
    # Render the edit form template
    return render_template('email_template_edit.html', title='Edit Email Template', form=form, template=tpl)

@main.route('/email_template/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_email_template(template_id):
    tpl = EmailTemplate.query.filter_by(id=template_id, company_id=current_user.company_id).first_or_404()
    db.session.delete(tpl)
    db.session.commit()
    flash('Template deleted.', 'success')
    return redirect(url_for('main.email_templates'))

# set a template as the default
@main.route('/email_template/<int:template_id>/set_default', methods=['POST'])
@login_required
def set_default_email_template(template_id):
    tpl = EmailTemplate.query.filter_by(id=template_id, company_id=current_user.company_id).first_or_404()
    # unset others
    EmailTemplate.query.filter_by(company_id=current_user.company_id, is_default=True).update({'is_default': False})
    tpl.is_default = True
    db.session.commit()
    flash(f'"{tpl.name}" is now the default template.', 'success')
    return redirect(url_for('main.email_templates'))