# blueprints/__init__.py
# Import main from its own module to avoid circular imports
from producepricer.blueprints._blueprint import main

# Import all sub-modules so their @main.route decorators are registered
from producepricer.blueprints import auth, ai, raw_products, packaging, items, receiving, pricing, customers, company, email_templates