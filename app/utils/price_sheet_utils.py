# Copyright Cade Stocker 2026
from app import db
from app.models import PriceSheetBackup

def create_price_sheet_backup(sheet):
    """
    Creates a backup copy of the given PriceSheet.
    Should be called before applying changes to the sheet.
    """
    backup = PriceSheetBackup(
        original_price_sheet_id=sheet.id,
        name=sheet.name,
        date=sheet.date,
        company_id=sheet.company_id,
        customer_id=sheet.customer_id,
        items=list(sheet.items),
        valid_from=sheet.valid_from,
        valid_to=sheet.valid_to
    )
    db.session.add(backup)
    return backup
