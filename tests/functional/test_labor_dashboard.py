# Copyright Cade Stocker 2026
"""
Functional tests for the Labor Dashboard routes added in app/blueprints/labor.py.

Routes covered:
  GET  /labor/daily_logs                           → labor_daily_logs
  POST /labor/daily_logs/<id>/delete               → delete_labor_daily_log
  GET  /labor/pay_groups                           → labor_pay_groups
  POST /labor/pay_groups/create                    → create_labor_pay_group
  POST /labor/pay_groups/<id>/delete               → delete_labor_pay_group
  GET  /labor/weekly_entries                       → labor_weekly_entries
  POST /labor/weekly_entries/<id>/delete           → delete_labor_weekly_entry
  GET  /labor/film_usage                           → labor_film_usage
  POST /labor/film_usage/<id>/delete               → delete_labor_film_usage

Each section checks:
  - Auth gating (redirect to /login when unauthenticated)
  - Correct page content for empty and populated state
  - Data isolation (company A never sees company B's records)
  - Delete succeeds for own records, returns 404 for other companies' records
  - Filters (date range, pay_group_id, year) narrow results correctly
"""

import pytest
from datetime import date

from flask import url_for

from app import db
from app.models import Company, User, DailyLog, PayGroups, WeeklyLaborEntry, FilmUsage


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client(client, app):
    """Authenticated test client with its own company."""
    with app.app_context():
        company = Company(name="Labor Test Co", admin_email="labor@test.com")
        db.session.add(company)
        db.session.commit()

        user = User(
            first_name="Labor",
            last_name="Tester",
            email="labor@test.com",
            password="password123",
            company_id=company.id,
        )
        db.session.add(user)
        db.session.commit()

        company_id = company.id

    client.post(
        "/login",
        data={"email": "labor@test.com", "password": "password123"},
        follow_redirects=True,
    )

    yield client, company_id


@pytest.fixture
def other_company_id(app):
    """A second company with no relationship to the authenticated user."""
    with app.app_context():
        other = Company(name="Other Co", admin_email="other@other.com")
        db.session.add(other)
        db.session.commit()
        return other.id


def _make_daily_log(app, company_id, log_date=None):
    """Insert a DailyLog and return its id."""
    with app.app_context():
        log = DailyLog(
            company_id=company_id,
            date=log_date or date(2026, 1, 15),
            items=200,
            sales=5000.00,
            labor_hours=40.0,
            overtime_hours=2.0,
            payroll_cost=800.00,
            number_of_employees=5,
            labor_ratio=0.16,
            sales_over_labor_cost=6.25,
            average_man_hour_cost=20.0,
            average_case_cost=4.0,
            average_hours_per_employee=8.4,
        )
        db.session.add(log)
        db.session.commit()
        return log.id


def _make_pay_group(app, company_id, name="Full Time"):
    """Insert a PayGroups and return its id."""
    with app.app_context():
        pg = PayGroups(company_id=company_id, name=name, description="Test group")
        db.session.add(pg)
        db.session.commit()
        return pg.id


def _make_weekly_entry(app, company_id, pay_group_id, week_date=None):
    """Insert a WeeklyLaborEntry and return its id."""
    with app.app_context():
        entry = WeeklyLaborEntry(
            company_id=company_id,
            week_start_date=week_date or date(2026, 1, 13),
            pay_group_id=pay_group_id,
            regular_hours=160.0,
            overtime_hours=8.0,
            pay=3200.0,
            percent_of_sales=15.0,
            cost_per_hour=19.0,
            number_in_pay_group=4,
            number_with_overtime=1,
            average_hours_per_employee=40.0,
        )
        db.session.add(entry)
        db.session.commit()
        return entry.id


def _make_film_usage(app, company_id, month=3, year=2026):
    """Insert a FilmUsage and return its id."""
    with app.app_context():
        record = FilmUsage(
            company_id=company_id,
            month=month,
            year=year,
            number_of_cases=500,
            number_of_rolls=10,
        )
        db.session.add(record)
        db.session.commit()
        return record.id


# ===========================================================================
# Daily Logs – GET /labor/daily_logs
# ===========================================================================

class TestDailyLogsPage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/labor/daily_logs")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/daily_logs")
        assert response.status_code == 200
        assert b"Daily Labor Logs" in response.data

    def test_shows_empty_state_when_no_logs(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/daily_logs")
        assert response.status_code == 200
        assert b"No daily logs found" in response.data

    def test_displays_existing_daily_log(self, auth_client, app):
        client, company_id = auth_client
        _make_daily_log(app, company_id)

        response = client.get("/labor/daily_logs")
        assert response.status_code == 200
        assert b"2026-01-15" in response.data

    def test_does_not_show_other_company_logs(self, auth_client, app, other_company_id):
        client, _ = auth_client
        _make_daily_log(app, other_company_id, log_date=date(2026, 6, 1))

        response = client.get("/labor/daily_logs")
        # The other company's log date should not appear
        assert b"2026-06-01" not in response.data

    def test_date_filter_start_date(self, auth_client, app):
        client, company_id = auth_client
        _make_daily_log(app, company_id, log_date=date(2026, 1, 1))
        _make_daily_log(app, company_id, log_date=date(2026, 3, 1))

        response = client.get("/labor/daily_logs?start_date=2026-02-01")
        assert response.status_code == 200
        assert b"2026-03-01" in response.data
        assert b"2026-01-01" not in response.data

    def test_date_filter_end_date(self, auth_client, app):
        client, company_id = auth_client
        _make_daily_log(app, company_id, log_date=date(2026, 1, 1))
        _make_daily_log(app, company_id, log_date=date(2026, 3, 1))

        response = client.get("/labor/daily_logs?end_date=2026-01-31")
        assert response.status_code == 200
        assert b"2026-01-01" in response.data
        assert b"2026-03-01" not in response.data

    def test_invalid_date_shows_warning(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/daily_logs?start_date=not-a-date", follow_redirects=True)
        assert response.status_code == 200
        assert b"Invalid start date" in response.data


class TestDeleteDailyLog:

    def test_redirects_when_not_logged_in(self, client, app):
        log_id = _make_daily_log(app, 1)
        response = client.post(f"/labor/daily_logs/{log_id}/delete")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deletes_own_log(self, auth_client, app):
        client, company_id = auth_client
        log_id = _make_daily_log(app, company_id)

        response = client.post(f"/labor/daily_logs/{log_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert b"Daily log deleted" in response.data

        with app.app_context():
            assert db.session.get(DailyLog, log_id) is None

    def test_returns_404_for_other_company_log(self, auth_client, app, other_company_id):
        client, _ = auth_client
        other_log_id = _make_daily_log(app, other_company_id)

        response = client.post(f"/labor/daily_logs/{other_log_id}/delete")
        assert response.status_code == 404


# ===========================================================================
# Pay Groups – GET /labor/pay_groups
# ===========================================================================

class TestPayGroupsPage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/labor/pay_groups")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/pay_groups")
        assert response.status_code == 200
        assert b"Pay Groups" in response.data

    def test_shows_empty_state_when_no_groups(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/pay_groups")
        assert b"No pay groups" in response.data

    def test_displays_existing_pay_group(self, auth_client, app):
        client, company_id = auth_client
        _make_pay_group(app, company_id, name="Managers")

        response = client.get("/labor/pay_groups")
        assert b"Managers" in response.data

    def test_does_not_show_other_company_groups(self, auth_client, app, other_company_id):
        client, _ = auth_client
        _make_pay_group(app, other_company_id, name="OtherCompanyGroup")

        response = client.get("/labor/pay_groups")
        assert b"OtherCompanyGroup" not in response.data


class TestCreatePayGroup:

    def test_redirects_when_not_logged_in(self, client):
        response = client.post("/labor/pay_groups/create", data={"name": "Temps"})
        assert response.status_code == 302
        assert "/login" in response.location

    def test_creates_pay_group(self, auth_client, app):
        client, company_id = auth_client
        response = client.post(
            "/labor/pay_groups/create",
            data={"name": "Temps", "description": "Temporary workers"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Temps" in response.data
        assert b"success" in response.data.lower()

        with app.app_context():
            pg = PayGroups.query.filter_by(company_id=company_id, name="Temps").first()
            assert pg is not None
            assert pg.description == "Temporary workers"

    def test_rejects_empty_name(self, auth_client):
        client, _ = auth_client
        response = client.post(
            "/labor/pay_groups/create",
            data={"name": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Pay group name is required" in response.data

    def test_rejects_duplicate_name(self, auth_client, app):
        client, company_id = auth_client
        _make_pay_group(app, company_id, name="Full Time")

        response = client.post(
            "/labor/pay_groups/create",
            data={"name": "Full Time"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"already exists" in response.data

    def test_allows_same_name_for_different_company(self, auth_client, app, other_company_id):
        """Pay group names are scoped per company — another company's names don't conflict."""
        client, company_id = auth_client
        _make_pay_group(app, other_company_id, name="SharedName")

        response = client.post(
            "/labor/pay_groups/create",
            data={"name": "SharedName"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"SharedName" in response.data


class TestDeletePayGroup:

    def test_redirects_when_not_logged_in(self, client, app):
        response = client.post("/labor/pay_groups/1/delete")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deletes_own_pay_group(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id, name="Seasonal")

        response = client.post(f"/labor/pay_groups/{pg_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert b"Seasonal" in response.data

        with app.app_context():
            assert db.session.get(PayGroups, pg_id) is None

    def test_blocks_delete_when_entries_exist(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id, name="Part Time")
        _make_weekly_entry(app, company_id, pg_id)

        response = client.post(f"/labor/pay_groups/{pg_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert b"Cannot delete" in response.data

        with app.app_context():
            assert db.session.get(PayGroups, pg_id) is not None

    def test_returns_404_for_other_company_group(self, auth_client, app, other_company_id):
        client, _ = auth_client
        other_pg_id = _make_pay_group(app, other_company_id, name="OtherGroup")

        response = client.post(f"/labor/pay_groups/{other_pg_id}/delete")
        assert response.status_code == 404


# ===========================================================================
# Weekly Entries – GET /labor/weekly_entries
# ===========================================================================

class TestWeeklyEntriesPage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/labor/weekly_entries")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/weekly_entries")
        assert response.status_code == 200
        assert b"Weekly Labor Entries" in response.data

    def test_shows_empty_state_when_no_entries(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/weekly_entries")
        assert b"No weekly labor entries found" in response.data

    def test_displays_existing_entry(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id, name="Full Time")
        _make_weekly_entry(app, company_id, pg_id, week_date=date(2026, 2, 2))

        response = client.get("/labor/weekly_entries")
        assert response.status_code == 200
        assert b"2026-02-02" in response.data

    def test_does_not_show_other_company_entries(self, auth_client, app, other_company_id):
        client, _ = auth_client
        other_pg_id = _make_pay_group(app, other_company_id, name="OtherGroup")
        _make_weekly_entry(app, other_company_id, other_pg_id, week_date=date(2026, 5, 5))

        response = client.get("/labor/weekly_entries")
        assert b"2026-05-05" not in response.data

    def test_filter_by_start_date(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id)
        _make_weekly_entry(app, company_id, pg_id, week_date=date(2026, 1, 5))
        _make_weekly_entry(app, company_id, pg_id, week_date=date(2026, 4, 6))

        response = client.get("/labor/weekly_entries?start_date=2026-03-01")
        assert b"2026-04-06" in response.data
        assert b"2026-01-05" not in response.data

    def test_filter_by_end_date(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id)
        _make_weekly_entry(app, company_id, pg_id, week_date=date(2026, 1, 5))
        _make_weekly_entry(app, company_id, pg_id, week_date=date(2026, 4, 6))

        response = client.get("/labor/weekly_entries?end_date=2026-02-01")
        assert b"2026-01-05" in response.data
        assert b"2026-04-06" not in response.data

    def test_filter_by_pay_group(self, auth_client, app):
        client, company_id = auth_client
        pg_a = _make_pay_group(app, company_id, name="Group A")
        pg_b = _make_pay_group(app, company_id, name="Group B")
        _make_weekly_entry(app, company_id, pg_a, week_date=date(2026, 1, 5))
        _make_weekly_entry(app, company_id, pg_b, week_date=date(2026, 1, 12))

        response = client.get(f"/labor/weekly_entries?pay_group_id={pg_a}")
        assert response.status_code == 200
        assert b"Group A" in response.data
        # Group B's date should not appear (it's filtered out)
        assert b"2026-01-12" not in response.data

    def test_pay_group_dropdown_populated(self, auth_client, app):
        client, company_id = auth_client
        _make_pay_group(app, company_id, name="Managers")

        response = client.get("/labor/weekly_entries")
        assert b"Managers" in response.data


class TestDeleteWeeklyEntry:

    def test_redirects_when_not_logged_in(self, client):
        response = client.post("/labor/weekly_entries/1/delete")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deletes_own_entry(self, auth_client, app):
        client, company_id = auth_client
        pg_id = _make_pay_group(app, company_id)
        entry_id = _make_weekly_entry(app, company_id, pg_id)

        response = client.post(f"/labor/weekly_entries/{entry_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert b"Weekly labor entry deleted" in response.data

        with app.app_context():
            assert db.session.get(WeeklyLaborEntry, entry_id) is None

    def test_returns_404_for_other_company_entry(self, auth_client, app, other_company_id):
        client, _ = auth_client
        other_pg_id = _make_pay_group(app, other_company_id, name="Other Group")
        other_entry_id = _make_weekly_entry(app, other_company_id, other_pg_id)

        response = client.post(f"/labor/weekly_entries/{other_entry_id}/delete")
        assert response.status_code == 404


# ===========================================================================
# Film Usage – GET /labor/film_usage
# ===========================================================================

class TestFilmUsagePage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.get("/labor/film_usage")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_page_loads_for_authenticated_user(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/film_usage")
        assert response.status_code == 200
        assert b"Film Usage" in response.data

    def test_shows_empty_state_when_no_records(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/film_usage")
        assert b"No film usage records found" in response.data

    def test_displays_existing_record(self, auth_client, app):
        client, company_id = auth_client
        _make_film_usage(app, company_id, month=7, year=2026)

        response = client.get("/labor/film_usage")
        assert response.status_code == 200
        assert b"2026" in response.data
        assert b"500" in response.data  # number_of_cases

    def test_does_not_show_other_company_records(self, auth_client, app, other_company_id):
        client, company_id = auth_client
        # Give the other company a unique case count so we can detect leakage
        with app.app_context():
            record = FilmUsage(
                company_id=other_company_id,
                month=1,
                year=2025,
                number_of_cases=99999,
                number_of_rolls=1,
            )
            db.session.add(record)
            db.session.commit()

        response = client.get("/labor/film_usage")
        assert b"99999" not in response.data

    def test_year_filter(self, auth_client, app):
        client, company_id = auth_client
        _make_film_usage(app, company_id, month=1, year=2025)
        _make_film_usage(app, company_id, month=6, year=2026)

        response = client.get("/labor/film_usage?year=2025")
        assert response.status_code == 200
        assert b"2025" in response.data
        assert b"<td>2026</td>" not in response.data

    def test_year_dropdown_populated(self, auth_client, app):
        client, company_id = auth_client
        _make_film_usage(app, company_id, month=1, year=2024)

        response = client.get("/labor/film_usage")
        assert b"2024" in response.data

    def test_cases_per_roll_calculated(self, auth_client, app):
        client, company_id = auth_client
        _make_film_usage(app, company_id, month=1, year=2026)

        response = client.get("/labor/film_usage")
        # 500 cases / 10 rolls = 50.0
        assert b"50.0" in response.data


class TestDeleteFilmUsage:

    def test_redirects_when_not_logged_in(self, client):
        response = client.post("/labor/film_usage/1/delete")
        assert response.status_code == 302
        assert "/login" in response.location

    def test_deletes_own_record(self, auth_client, app):
        client, company_id = auth_client
        record_id = _make_film_usage(app, company_id)

        response = client.post(f"/labor/film_usage/{record_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert b"Film usage record deleted" in response.data

        with app.app_context():
            assert db.session.get(FilmUsage, record_id) is None

    def test_returns_404_for_other_company_record(self, auth_client, app, other_company_id):
        client, _ = auth_client
        other_record_id = _make_film_usage(app, other_company_id, month=2, year=2026)

        response = client.post(f"/labor/film_usage/{other_record_id}/delete")
        assert response.status_code == 404


# ===========================================================================
# Navbar – verify all Labor dropdown links render on authenticated pages
# ===========================================================================

class TestLaborNavbarLinks:

    def test_labor_dropdown_present_in_nav(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/daily_logs")
        assert b"Labor" in response.data

    def test_daily_logs_nav_link_present(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/daily_logs")
        assert b"Daily" in response.data

    def test_weekly_entries_nav_link_present(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/weekly_entries")
        assert b"Weekly" in response.data

    def test_pay_groups_nav_link_present(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/pay_groups")
        assert b"Pay Groups" in response.data

    def test_film_usage_nav_link_present(self, auth_client):
        client, _ = auth_client
        response = client.get("/labor/film_usage")
        assert b"Film Usage" in response.data
