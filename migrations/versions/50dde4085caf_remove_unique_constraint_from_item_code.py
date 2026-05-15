"""remove_unique_constraint_from_item_code

Revision ID: 50dde4085caf
Revises: bd4a05877bca
Create Date: 2025-12-30 14:45:34.576891

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '50dde4085caf'
down_revision = 'bd4a05877bca'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support dropping constraints directly, so we need to recreate the table
    # Step 1: Create new table without the UNIQUE constraint on code
    op.execute("""
    CREATE TABLE item_new (
        id INTEGER NOT NULL, 
        name VARCHAR(100) NOT NULL, 
        code VARCHAR(100) NOT NULL, 
        unit_of_weight VARCHAR(8) NOT NULL, 
        packaging_id INTEGER NOT NULL, 
        company_id INTEGER NOT NULL, 
        ranch BOOLEAN DEFAULT 0 NOT NULL, 
        case_weight FLOAT DEFAULT (0.0) NOT NULL,
        item_designation VARCHAR(11) DEFAULT 'FOODSERVICE' NOT NULL,
        alternate_code VARCHAR(100),
        PRIMARY KEY (id), 
        FOREIGN KEY(packaging_id) REFERENCES packaging (id), 
        FOREIGN KEY(company_id) REFERENCES company (id)
    )
    """)
    
    # Step 2: Copy data from old table to new table
    op.execute("""
    INSERT INTO item_new (id, name, code, unit_of_weight, packaging_id, company_id, 
                         ranch, case_weight, item_designation, alternate_code)
    SELECT id, name, code, unit_of_weight, packaging_id, company_id, 
           ranch, case_weight, item_designation, alternate_code
    FROM item
    """)
    
    # Step 3: Drop old table
    op.execute("DROP TABLE item")
    
    # Step 4: Rename new table to item
    op.execute("ALTER TABLE item_new RENAME TO item")


def downgrade():
    # Recreate the table with the UNIQUE constraint
    op.execute("""
    CREATE TABLE item_new (
        id INTEGER NOT NULL, 
        name VARCHAR(100) NOT NULL, 
        code VARCHAR(100) NOT NULL, 
        unit_of_weight VARCHAR(8) NOT NULL, 
        packaging_id INTEGER NOT NULL, 
        company_id INTEGER NOT NULL, 
        ranch BOOLEAN DEFAULT 0 NOT NULL, 
        case_weight FLOAT DEFAULT (0.0) NOT NULL,
        item_designation VARCHAR(11) DEFAULT 'FOODSERVICE' NOT NULL,
        alternate_code VARCHAR(100),
        PRIMARY KEY (id), 
        FOREIGN KEY(packaging_id) REFERENCES packaging (id), 
        UNIQUE (code),
        FOREIGN KEY(company_id) REFERENCES company (id)
    )
    """)
    
    op.execute("""
    INSERT INTO item_new (id, name, code, unit_of_weight, packaging_id, company_id, 
                         ranch, case_weight, item_designation, alternate_code)
    SELECT id, name, code, unit_of_weight, packaging_id, company_id, 
           ranch, case_weight, item_designation, alternate_code
    FROM item
    """)
    
    op.execute("DROP TABLE item")
    op.execute("ALTER TABLE item_new RENAME TO item")
