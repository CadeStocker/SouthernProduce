# Copyright Cade Stocker 2026
# blueprints/__init__.py
# Import main from its own module to avoid circular imports
from app.blueprints._blueprint import main

# Import all sub-modules so their @main.route decorators are registered
from app.blueprints import ai, auth, company, customers, email_templates, inventory, items, labor, notifications, packaging, pricing, raw_products, receiving, insights