"""Seed fake inventory sessions into the local database.

Usage:
    python scripts/seed_fake_inventory.py [num_sessions] [company_id]

Defaults: 5 sessions for company_id=1.

It will ensure a small catalog of items/supplies exists (creating some if the
company has too few), then generate inventory sessions with random line-item
counts spread over the past few months. Safe to re-run; it only appends.
"""
import random
import sys
from datetime import datetime, timedelta

from app import create_app
from app.models import db
from app.models.auth import Company
from app.models.core import Packaging
from app.models.inventory import (
    Item, UnitOfWeight, Supply, InventorySession, ItemInventory, SupplyInventory,
)

# Deterministic-ish but varied output
random.seed()

COUNTERS = ["Alice Nguyen", "Bob Carter", "Cody Reyes", "Dana White", "Evan Brooks"]
SAMPLE_ITEMS = [
    ("Diced Onions", "DON-12"),
    ("Shredded Lettuce", "SLT-05"),
    ("Carrot Sticks", "CST-08"),
    ("Cole Slaw Mix", "CSM-20"),
    ("Pico de Gallo", "PDG-16"),
]
SAMPLE_SUPPLIES = [
    ("Cardboard Boxes", "boxes", "Packaging"),
    ("Poly Bags", "bags", "Packaging"),
    ("Pallet Wrap", "rolls", "Shipping"),
    ("Labels", "rolls", "Packaging"),
]


def ensure_catalog(company_id):
    """Make sure there are at least a handful of items and supplies to count."""
    items = Item.query.filter_by(company_id=company_id).all()
    if len(items) < 3:
        packaging = Packaging.query.filter_by(company_id=company_id).first()
        if packaging is None:
            packaging = Packaging(packaging_type="Case", company_id=company_id)
            db.session.add(packaging)
            db.session.flush()
        for name, code in SAMPLE_ITEMS:
            if not Item.query.filter_by(company_id=company_id, code=code).first():
                db.session.add(Item(
                    name=name, code=code, unit_of_weight=UnitOfWeight.POUND,
                    packaging_id=packaging.id, company_id=company_id, case_weight=20.0,
                ))
        db.session.flush()
        items = Item.query.filter_by(company_id=company_id).all()

    supplies = Supply.query.filter_by(company_id=company_id).all()
    if len(supplies) < 2:
        for name, unit, category in SAMPLE_SUPPLIES:
            if not Supply.query.filter_by(company_id=company_id, name=name).first():
                db.session.add(Supply(
                    name=name, unit=unit, company_id=company_id, category=category,
                ))
        db.session.flush()
        supplies = Supply.query.filter_by(company_id=company_id).all()

    return items, supplies


def seed(num_sessions, company_id):
    company = Company.query.get(company_id)
    if company is None:
        raise SystemExit(f"No company with id={company_id}. Existing: "
                         f"{[(c.id, c.name) for c in Company.query.all()]}")

    items, supplies = ensure_catalog(company_id)
    now = datetime.utcnow()

    created = []
    for i in range(num_sessions):
        submitted = now - timedelta(days=random.randint(0, 120),
                                    hours=random.randint(0, 23))
        counter = random.choice(COUNTERS)
        session = InventorySession(
            company_id=company_id,
            counted_by=counter,
            label=f"{submitted.strftime('%b %d, %Y')} Count",
            notes=random.choice(["", "", "End of month count", "Spot check", "Quarterly"]),
            submitted_at=submitted,
        )
        db.session.add(session)
        db.session.flush()  # assign session.id

        # Count a random subset of items
        for item in random.sample(items, k=random.randint(1, len(items))):
            db.session.add(ItemInventory(
                item_id=item.id, quantity=random.randint(0, 250),
                company_id=company_id, session_id=session.id,
                count_date=submitted, counted_by=counter,
            ))
        # Count a random subset of supplies
        for supply in random.sample(supplies, k=random.randint(0, len(supplies))):
            db.session.add(SupplyInventory(
                supply_id=supply.id, quantity=round(random.uniform(0, 500), 1),
                company_id=company_id, session_id=session.id,
                count_date=submitted, counted_by=counter,
            ))
        created.append(session)

    db.session.commit()
    print(f"Created {len(created)} inventory sessions for company "
          f"'{company.name}' (id={company_id}):")
    for s in created:
        print(f"  - #{s.id} {s.label!r} by {s.counted_by} "
              f"({len(s.item_counts)} items, {len(s.supply_counts)} supplies)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cid = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    app = create_app()
    with app.app_context():
        seed(n, cid)
