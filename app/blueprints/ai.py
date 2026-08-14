# Copyright Cade Stocker 2026
import datetime
from flask_mailman import EmailMessage
from app.utils.pdf_utils import extract_pdf_text
from app.utils.matching import best_match, match_parsed_items, build_quick_entry_list, normalize_name
from app.utils.parsing import coerce_iso_date, parse_price_list_with_openai
from app.blueprints._blueprint import main

from flask import (
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    flash,
    current_app
)
from itsdangerous import BadSignature, Serializer, SignatureExpired
from app.models import (
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
    Packaging, 
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
from app.forms import(
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
from app import db, bcrypt
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_mailman import EmailMessage
from app.utils.ai_utils import get_ai_response
from app.utils.qr_utils import generate_api_key_qr_code, generate_qr_code_bytes
import pdfplumber
import tempfile
from sqlalchemy import func

@main.route('/api/item/<int:item_id>/summarize', methods=['POST'])
@login_required
def summarize_item(item_id):
    """Generates an AI-powered summary for a specific item."""

    # get the item from the database
    item = Item.query.filter_by(id=item_id, company_id=current_user.company_id).first_or_404()

    # 1. Gather all data for the prompt
    costs = ItemTotalCost.query.filter_by(item_id=item.id).order_by(ItemTotalCost.date.asc()).all()
    infos = ItemInfo.query.filter_by(item_id=item.id).order_by(ItemInfo.date.asc()).all()
    prices = PriceHistory.query.filter_by(item_id=item.id).order_by(PriceHistory.date.asc()).all()
    customer_map = {c.id: c.name for c in Customer.query.filter_by(company_id=current_user.company_id).all()}

    # 2. Build the prompt string
    prompt = f"Please provide a brief executive summary for the produce item '{item.name}' ({item.code}).\n\n"
    prompt += "Here is the historical data:\n\n"

    if costs:
        prompt += "Cost History (Total cost per case):\n"
        for c in costs:
            prompt += f"- {c.date.strftime('%Y-%m-%d')}: ${c.total_cost:.2f}\n"
        prompt += "\n"

    if infos:
        prompt += "Yield and Labor History (the yield is how much product is obtained from a given amount of input aka raw product):\n"
        for i in infos:
            prompt += f"- {i.date.strftime('%Y-%m-%d')}: Yield={i.product_yield:.2f}%, Labor Hours={i.labor_hours:.2f}\n"
        prompt += "\n"

    if prices:
        prompt += "Price History (Sale price per case):\n"
        for p in prices:
            customer_name = customer_map.get(p.customer_id, "General")
            prompt += f"- {p.date.strftime('%Y-%m-%d')}: ${p.price:.2f} (Customer: {customer_name})\n"
        prompt += "\n"

    prompt += """
Based on this data, please analyze the following points and provide actionable insights:
1.  **Cost Trend:** Is the overall cost to produce this item increasing, decreasing, or stable?
2.  **Profitability Analysis:** How are the pricing decisions affecting profit margins over time? Are we adjusting prices correctly in response to cost changes?
3.  **Key Insights & Anomalies:** Are there any sudden spikes or drops in cost, price, or yield that are noteworthy?
4.  **Actionable Recommendation:** Suggest one clear, data-driven action that could be taken to improve profitability or efficiency for this item.
"""

    # 3. Get the AI response
    result = get_ai_response(prompt, system_message="You are a professional produce pricing analyst providing data-driven insights.")

    if result["success"]:
        # save the response
        try:
            summary = result["content"]
            response = AIResponse(content=summary, date=datetime.datetime.utcnow(), company_id=current_user.company_id, name=f"Summary for {item.name} ({item.code})")
            db.session.add(response)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Optionally log this error, but don't block the user
            print(f"Error saving AI response to DB: {e}")
        
        return jsonify({"success": True, "summary": result["content"]})
    else:
        return jsonify({"success": False, "error": result.get("error", "An unknown error occurred.")}), 500

@main.route('/ai-assistant')
@login_required
def ai_assistant():
    """Render the AI assistant page"""
    return render_template('ai_assistant.html', title="AI Assistant")

@main.route('/api/ai-chat', methods=['POST'])
@login_required
def ai_chat():
    """Handle API requests to the AI"""
    data = request.get_json()
    
    if not data or 'prompt' not in data:
        # FIX: Return a proper JSON error response
        return jsonify({"success": False, "error": "Invalid request. Prompt is missing."}), 400
    
    # Get response from OpenAI
    result = get_ai_response(data['prompt'])
    
    if result["success"]:
        return jsonify({"success": True, "response": result["content"]})
    else:
        # FIX: Return a proper JSON error response
        return jsonify({"success": False, "error": result.get("error", "An unknown error occurred.")}), 500

@main.route('/ai-summaries')
@login_required
def ai_summaries():
    """Displays a paginated list of past AI-generated summaries."""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of summaries per page

    summaries_pagination = AIResponse.query.filter_by(
        company_id=current_user.company_id
    ).order_by(
        AIResponse.date.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'ai_summaries.html',
        title='AI Summary History',
        summaries_pagination=summaries_pagination
    )

@main.route('/delete_ai_summary/<int:summary_id>', methods=['POST'])
@login_required
def delete_ai_summary(summary_id):
    """Deletes an AI summary."""
    summary = AIResponse.query.filter_by(
        id=summary_id,
        company_id=current_user.company_id
    ).first_or_404()

    db.session.delete(summary)
    db.session.commit()
    flash('AI summary has been deleted.', 'success')
    return redirect(url_for('main.ai_summaries'))

@main.route('/api/raw-product/<int:raw_product_id>/summarize', methods=['POST'])
@login_required
def summarize_raw_product(raw_product_id):
    """Generates an AI-powered summary for a specific raw product."""
    raw_product = RawProduct.query.filter_by(id=raw_product_id, company_id=current_user.company_id).first_or_404()

    # 1. Gather all data for the prompt
    costs = CostHistory.query.filter_by(raw_product_id=raw_product.id).order_by(CostHistory.date.asc()).all()
    items_using = Item.query.filter(Item.raw_products.any(id=raw_product.id)).all()

    # 2. Build the prompt string
    prompt = f"Please provide a brief executive summary for the raw produce material '{raw_product.name}'.\n\n"
    prompt += "Here is the historical data:\n\n"

    if costs:
        prompt += "Cost History (Price per unit from supplier):\n"
        for c in costs:
            prompt += f"- {c.date.strftime('%Y-%m-%d')}: ${c.cost:.2f}\n"
        prompt += "\n"
    else:
        prompt += "No cost history is available for this raw product.\n\n"

    if items_using:
        prompt += "This raw product is currently used as an ingredient in the following finished items:\n"
        for item in items_using:
            prompt += f"- {item.name} ({item.code})\n"
        prompt += "\n"
    else:
        prompt += "This raw product is not currently used in any finished items.\n\n"

    prompt += """
Based on this data, please analyze the following points and provide actionable insights:
1.  **Cost Trend:** Is the cost of this raw material increasing, decreasing, or stable over time?
2.  **Impact Analysis:** How do fluctuations in this material's cost affect the total cost of the finished goods that depend on it?
3.  **Key Insights & Anomalies:** Are there any sudden spikes or drops in cost that are noteworthy?
4.  **Actionable Recommendation:** Suggest one clear, data-driven action. For example, should we explore alternative suppliers, consider a substitute material, or is the price stable enough to negotiate a long-term contract?
"""

    # 3. Get the AI response
    result = get_ai_response(prompt, system_message="You are a professional supply chain analyst for a produce company, specializing in raw material costs.")

    if result["success"]:
        # save the response to the database
        try:
            summary = result["content"]
            response = AIResponse(
                content=summary,
                date=datetime.datetime.utcnow(),
                company_id=current_user.company_id,
                name=f"Raw Product Summary for {raw_product.name}"
            )
            db.session.add(response)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error saving AI response to DB: {e}")

        return jsonify({"success": True, "summary": result["content"]})
    else:
        return jsonify({"success": False, "error": result.get("error", "An unknown error occurred.")}, 500)


@main.route('/api/packaging/<int:packaging_id>/summarize', methods=['POST'])
@login_required
def summarize_packaging(packaging_id):
    """Generates an AI-powered summary for a specific packaging."""
    packaging = Packaging.query.filter_by(id=packaging_id, company_id=current_user.company_id).first_or_404()

    # 1. Gather all data for the prompt
    costs = PackagingCost.query.filter_by(packaging_id=packaging.id).order_by(PackagingCost.date.asc()).all()
    items_using = Item.query.filter_by(packaging_id=packaging.id, company_id=current_user.company_id).all()

    # 2. Build the prompt string
    prompt = f"Please provide a brief executive summary for the packaging material '{packaging.packaging_type}'.\n\n"
    prompt += "Here is the historical data:\n\n"

    if costs:
        prompt += "Cost History (Total cost per unit):\n"
        for c in costs:
            total_cost = c.box_cost + c.bag_cost + c.tray_andor_chemical_cost + c.label_andor_tape_cost
            prompt += f"- {c.date.strftime('%Y-%m-%d')}: total cost:${total_cost:.2f} box cost:${c.box_cost:.2f} bag cost:${c.bag_cost:.2f} tray/chemical cost:${c.tray_andor_chemical_cost:.2f} label/tape cost:${c.label_andor_tape_cost:.2f}\n"
        prompt += "\n"
    else:
        prompt += "No cost history is available for this packaging.\n\n"

    if items_using:
        prompt += "This packaging is currently used by the following items:\n"
        for item in items_using:
            prompt += f"- {item.name} ({item.code})\n"
        prompt += "\n"
    else:
        prompt += "This packaging is not currently used by any items.\n\n"

    prompt += """
Based on this data, please analyze the following points and provide actionable insights:
1.  **Cost Trend:** Is the cost of this packaging increasing, decreasing, or stable over time?
2.  **Impact Analysis:** How do changes in this packaging's cost affect the profitability of the items that use it?
3.  **Key Insights & Anomalies:** Are there any sudden spikes or drops in cost that are noteworthy?
4.  **Actionable Recommendation:** Suggest one clear, data-driven action. For example, should we look for alternative suppliers, or is the cost stable enough to lock in a price?
"""

    # 3. Get the AI response
    result = get_ai_response(prompt, system_message="You are a professional supply chain analyst for a produce company, specializing in packaging costs.")

    if result["success"]:
        # save the response to the database
        try:
            summary = result["content"]
            response = AIResponse(content=summary, date=datetime.datetime.utcnow(), company_id=current_user.company_id, name=f"Packaging Summary for {packaging.packaging_type}")
            db.session.add(response)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Optionally log this error, but don't block the user
            print(f"Error saving AI response to DB: {e}")
        # return the summary as JSON
        return jsonify({"success": True, "summary": result["content"]})
    else:
        return jsonify({"success": False, "error": result.get("error", "An unknown error occurred.")}, 500)
    
# Utility function to extract text from PDF
@main.route('/api/parse_price_pdf', methods=['POST'])
@login_required
def parse_price_pdf():
    """
    Step 1: Parses a PDF and returns the matched/unmatched items for user review WITHOUT saving.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file"}), 400

    try:
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            f.save(tf.name)
            pdf_path = tf.name

        pdf_text = extract_pdf_text(pdf_path)
        
        # Make sure pdf_text is not None
        if not pdf_text:
            return jsonify({"error": "Could not extract text from PDF"}), 400
        
        # Add size limit to prevent timeout
        if len(pdf_text) > 15000:
            pdf_text = pdf_text[:15000] + "\n[Text truncated due to length...]"
            
        parsed = parse_price_list_with_openai(pdf_text)

        # print(f"PDF text extracted: {pdf_text[:100]}...")  # First 100 chars
        # print(f"AI response: {parsed}")

        # Clean up temp file
        try:
            os.remove(pdf_path)
        except OSError:
            pass

        if "error" in parsed:
            return jsonify({"error": parsed["error"]}), 500

        effective_date = coerce_iso_date(parsed.get("effective_date"))
        items = parsed.get("items", [])
        vendor = parsed.get("vendor", "").strip() or "Unknown Vendor"

        # Process items as before...
        company_id = current_user.company_id
        all_products = db.session.query(RawProduct.id, RawProduct.name).filter(RawProduct.company_id == company_id).all()
        name_map = {name: rid for (rid, name) in all_products}
        candidate_names = list(name_map.keys());

        # Build a unified parsed_items list with inline candidate suggestions.
        parsed_items = []

        # Track which candidate id is already used by which parsed item (by index)
        in_use_by = {}

        # For each parsed item, compute top matches and annotate
        from app.utils.matching import top_n_matches

        for idx, it in enumerate(items, start=1):
            name = (it.get("name") or "").strip()
            price = it.get("price_usd")
            norm = normalize_name(name)

            top = top_n_matches(name, candidate_names, n=5, min_score=0)

            matched_product_id = None
            matched_product_name = None
            match_score = None

            if top:
                # Best candidate
                best_name, best_score = top[0]
                best_id = name_map.get(best_name)
                if best_score >= 60:
                    matched_product_name = best_name
                    matched_product_id = best_id
                    match_score = best_score
                    # mark usage
                    if best_id:
                        in_use_by[best_id] = idx

            # Build candidate objects (do not filter out ones that are in use,
            # but annotate them so UI can warn the reviewer)
            cand_objs = []
            for c in top:
                cname, cscore = c
                cid = name_map.get(cname)
                cand_objs.append({
                    "id": cid,
                    "name": cname,
                    "score": cscore,
                    "in_use_by": in_use_by.get(cid)
                })

            parsed_items.append({
                "id": idx,
                "name_from_pdf": name,
                "price_from_pdf": price,
                "normalized_name": norm,
                "matched_product_id": matched_product_id,
                "matched_product_name": matched_product_name,
                "match_score": match_score,
                "candidates": cand_objs
            })

        # Now that we have parsed_items and in_use_by annotations, create
        # backward-compatible matched_items and skipped_items for existing UI/tests.
        matched_items = []
        skipped_items = []
        unmatched_quick = []

        for p in parsed_items:
            if p.get('matched_product_id'):
                matched_items.append({
                    "name_from_pdf": p.get('name_from_pdf'),
                    "price_from_pdf": p.get('price_from_pdf'),
                    "matched_product_name": p.get('matched_product_name'),
                    "matched_product_id": p.get('matched_product_id'),
                    "match_score": p.get('match_score')
                })
            else:
                # build suggestions for skipped_items using candidate objects
                sug = [{"name": c['name'], "id": c['id'], "score": c['score']} for c in p.get('candidates', [])]
                skipped_items.append({
                    "name": p.get('name_from_pdf'),
                    "price_from_pdf": p.get('price_from_pdf'),
                    "reason": "no_confident_match",
                    "suggestions": sug
                })
                unmatched_quick.append({"name_from_pdf": p.get('name_from_pdf'), "price_from_pdf": p.get('price_from_pdf')})

        # Sort parsed_items alphabetically by normalized_name for UI scanning
        parsed_items.sort(key=lambda x: x.get('normalized_name') or '')

        # Also sort matched and skipped for compatibility/consistency
        matched_items.sort(key=lambda x: normalize_name(x.get('matched_product_name') or x.get('name_from_pdf') or ''))
        skipped_items.sort(key=lambda x: normalize_name(x.get('name') or ''))

        quick_entry = build_quick_entry_list(unmatched_quick)

        # Export candidate list (id+name) sorted alphabetically
        candidates_list = sorted([{"id": rid, "name": name} for (name, rid) in name_map.items()], key=lambda x: normalize_name(x['name']))

        return jsonify({
            "vendor": vendor,
            "effective_date": effective_date.isoformat(),
            "parsed_items": parsed_items,
            "matched_items": matched_items,
            "skipped_items": skipped_items,
            "quick_entry": quick_entry,
            "candidates": candidates_list
        })

    except Exception as e:
        print(f"PDF processing error: {str(e)}")
        return jsonify({"error": f"PDF processing error: {str(e)}"}), 500
    
# Helper function to extract text from PDF using pdfplumber
@main.route('/api/save_parsed_prices', methods=['POST'])
@login_required
def save_parsed_prices():
    """
    Step 2: Receives reviewed data from the frontend and saves it to the database.
    """
    data = request.get_json()
    items_to_create = data.get('items_to_create', [])
    effective_date = coerce_iso_date(data.get('effective_date'))
    company_id = current_user.company_id
    
    created_count = 0
    skipped_count = 0

    for item in items_to_create:
        raw_product_id = item.get('matched_product_id')
        price = item.get('price_from_pdf')

        # If the frontend didn't provide an existing raw_product_id, try to
        # resolve by exact name; if not found, create a new RawProduct so the
        # price can be stored against a product record.
        if not raw_product_id:
            candidate_name = (item.get('matched_product_name') or item.get('name_from_pdf') or '').strip()
            if candidate_name:
                existing = RawProduct.query.filter_by(name=candidate_name, company_id=company_id).first()
                if existing:
                    raw_product_id = existing.id
                else:
                    # create a minimal RawProduct record
                    rp = RawProduct(name=candidate_name, company_id=company_id)
                    db.session.add(rp)
                    # Flush so we get an id without committing the whole transaction
                    db.session.flush()
                    raw_product_id = rp.id

        # Final check for duplicates before inserting
        exists = db.session.query(CostHistory.id).filter(
            CostHistory.company_id == company_id,
            CostHistory.raw_product_id == raw_product_id,
            CostHistory.date == effective_date,
            func.abs(CostHistory.cost - float(price)) < 0.001
        ).first()

        if exists:
            skipped_count += 1
            continue

        ch = CostHistory(
            cost=float(price),
            date=effective_date,
            company_id=company_id,
            raw_product_id=raw_product_id,
        )
        db.session.add(ch)
        created_count += 1

    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Successfully created {created_count} new cost entries. Skipped {skipped_count} duplicates."
    })