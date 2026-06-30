# Copyright Cade Stocker 2026

"""
Models for the labor app api I'm creating
"""

from app import db

class DailyLog(db.Model):
    """Model for daily labor logs."""
    __tablename__ = 'daily_log'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    items = db.Column(db.Integer, nullable=False)
    sales = db.Column(db.Float, nullable=False)
    labor_hours = db.Column(db.Float, nullable=False)
    overtime_hours = db.Column(db.Float, nullable=False)
    payroll_cost = db.Column(db.Float, nullable=False)
    number_of_employees = db.Column(db.Integer, nullable=False)
    labor_ratio = db.Column(db.Float, nullable=False)
    sales_over_labor_cost = db.Column(db.Float, nullable=False)
    average_man_hour_cost = db.Column(db.Float, nullable=False)
    average_case_cost = db.Column(db.Float, nullable=False)
    average_hours_per_employee = db.Column(db.Float, nullable=False)

    def __init__(self, company_id, date, items, sales, labor_hours, overtime_hours, payroll_cost, number_of_employees, labor_ratio, sales_over_labor_cost, average_man_hour_cost, average_case_cost, average_hours_per_employee):
        self.company_id = company_id
        self.date = date
        self.items = items
        self.sales = sales
        self.labor_hours = labor_hours
        self.overtime_hours = overtime_hours
        self.payroll_cost = payroll_cost
        self.number_of_employees = number_of_employees
        self.labor_ratio = labor_ratio
        self.sales_over_labor_cost = sales_over_labor_cost
        self.average_man_hour_cost = average_man_hour_cost
        self.average_case_cost = average_case_cost
        self.average_hours_per_employee = average_hours_per_employee

    def __repr__(self):
        return f"DailyLog('{self.company_id}', '{self.date}', '{self.items}', '{self.sales}', '{self.labor_hours}', '{self.overtime_hours}', '{self.payroll_cost}', '{self.number_of_employees}', '{self.labor_ratio}', '{self.sales_over_labor_cost}', '{self.average_man_hour_cost}', '{self.average_case_cost}', '{self.average_hours_per_employee}')"
    
class PayGroups(db.Model):
    """Model for pay groups."""
    __tablename__ = 'pay_groups'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    def __init__(self, company_id, name, description=None):
        self.company_id = company_id
        self.name = name
        self.description = description

    def __repr__(self):
        return f"PayGroups('{self.name}', '{self.description}')"

"""THINK I'LL USE DESIGNATION COSTS FOR THIS (ALREADY HAS SNACKPACK AND BULK)"""
# class ItemType(db.Model):
#     """Model for item types."""
#     __tablename__ = 'item_type'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     description = db.Column(db.String(255), nullable=True)

#     def __init__(self, name, description=None):
#         self.name = name
#         self.description = description

#     def __repr__(self):
#         return f"ItemType('{self.name}', '{self.description}')"

class WeeklyLaborEntry(db.Model):
    """Model for weekly labor summaries."""

    __tablename__ = 'weekly_labor_summary'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    pay_group_id = db.Column(db.Integer, db.ForeignKey('pay_groups.id'), nullable=False)
    regular_hours = db.Column(db.Float, nullable=False)
    overtime_hours = db.Column(db.Float, nullable=False)
    pay = db.Column(db.Float, nullable=False)
    percent_of_sales = db.Column(db.Float, nullable=False)
    cost_per_hour = db.Column(db.Float, nullable=False)
    number_in_pay_group = db.Column(db.Integer, nullable=False)
    number_with_overtime = db.Column(db.Integer, nullable=False)
    average_hours_per_employee = db.Column(db.Float, nullable=False)

    def __init__(self, company_id, week_start_date, pay_group_id, regular_hours, overtime_hours, pay, percent_of_sales, cost_per_hour, number_in_pay_group, number_with_overtime, average_hours_per_employee):
        self.company_id = company_id
        self.week_start_date = week_start_date
        self.pay_group_id = pay_group_id
        self.regular_hours = regular_hours
        self.overtime_hours = overtime_hours
        self.pay = pay
        self.percent_of_sales = percent_of_sales
        self.cost_per_hour = cost_per_hour
        self.number_in_pay_group = number_in_pay_group
        self.number_with_overtime = number_with_overtime
        self.average_hours_per_employee = average_hours_per_employee

    def __repr__(self):
        return f"WeeklyLaborEntry('{self.week_start_date}', '{self.pay_group_id}', '{self.regular_hours}', '{self.overtime_hours}', '{self.pay}', '{self.percent_of_sales}', '{self.cost_per_hour}', '{self.number_in_pay_group}', '{self.number_with_overtime}', '{self.average_hours_per_employee}')"
    
class SalesByDesignation(db.Model):
    """Model for sales by item type."""
    __tablename__ = 'sales_by_item_type'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    item_designation_id = db.Column(db.Integer, db.ForeignKey('designation_cost.id'), nullable=False)
    number_of_items = db.Column(db.Integer, nullable=False)
    sales = db.Column(db.Float, nullable=False)
    average_price_per_item = db.Column(db.Float, nullable=False)
    percent_of_total_sales = db.Column(db.Float, nullable=False)
    percent_of_total_boxes = db.Column(db.Float, nullable=False)

    def __init__(self, company_id, date, item_designation_id, number_of_items, sales, average_price_per_item, percent_of_total_sales, percent_of_total_boxes):
        self.company_id = company_id
        self.date = date
        self.item_designation_id = item_designation_id
        self.number_of_items = number_of_items
        self.sales = sales
        self.average_price_per_item = average_price_per_item
        self.percent_of_total_sales = percent_of_total_sales
        self.percent_of_total_boxes = percent_of_total_boxes

    def __repr__(self):
        return f"SalesByDesignation('{self.date}', '{self.item_designation_id}', '{self.number_of_items}', '{self.sales}', '{self.average_price_per_item}', '{self.percent_of_total_sales}', '{self.percent_of_total_boxes}')"
    
class FilmUsage(db.Model):
    """Model for film usage."""
    __tablename__ = 'film_usage'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    number_of_cases = db.Column(db.Integer, nullable=False)
    number_of_rolls = db.Column(db.Integer, nullable=False)

    def __init__(self, company_id, month, year, number_of_cases, number_of_rolls):
        self.company_id = company_id
        self.month = month
        self.year = year
        self.number_of_cases = number_of_cases
        self.number_of_rolls = number_of_rolls