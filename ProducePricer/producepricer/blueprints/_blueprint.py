from flask import Blueprint

# The single 'main' Blueprint instance shared by all sub-modules.
# Kept in its own file to avoid circular imports: sub-modules import
# from here, and __init__.py also imports from here.
main = Blueprint('main', __name__)
