# Copyright Cade Stocker 2026
"""
Tests that update_item_total_cost records a cost_margin fact alongside the
ItemTotalCost row it writes. This is the only fact writer wired into a
blueprint helper rather than an API route, so it is covered separately.
"""

import pytest
from types import SimpleNamespace

from app import db
from app.blueprints import items as items_module
from app.models import AnalyticsFact, ItemTotalCost


COST_TUPLE = (12.75, 2.5, 0.5, 1.25, 8.0, 0.5)  # cost, labor, designation, packaging, raw, ranch


@pytest.fixture
def cost_env(app, analytics_env, monkeypatch):
    """A committed item plus stubs for the login/cost dependencies."""
    db.session.commit()
    company_id = analytics_env.company.id
    item_id = analytics_env.item.id

    monkeypatch.setattr(
        items_module, 'current_user', SimpleNamespace(company_id=company_id)
    )

    with app.test_request_context():
        yield SimpleNamespace(company_id=company_id, item_id=item_id)


def _patch_cost(monkeypatch, value=COST_TUPLE):
    monkeypatch.setattr(items_module, 'calculate_item_cost', lambda item_id: value)


class TestUpdateItemTotalCostRecordsFact:
    """The happy path writes both the operational row and the fact."""

    def test_creates_a_cost_margin_fact(self, cost_env, monkeypatch):
        _patch_cost(monkeypatch)

        items_module.update_item_total_cost(cost_env.item_id)

        cost_row = ItemTotalCost.query.filter_by(item_id=cost_env.item_id).one()
        fact = AnalyticsFact.query.filter_by(fact_type='cost_margin').one()
        assert fact.source_table == 'item_total_cost'
        assert fact.source_id == cost_row.id
        assert fact.item_id == cost_env.item_id
        assert fact.company_id == cost_env.company_id
        assert fact.cost == 12.75
        assert fact.date == cost_row.date

    def test_repeated_updates_track_each_cost_row(self, cost_env, monkeypatch):
        """Each recalculation appends a new cost row, so each gets its own fact."""
        _patch_cost(monkeypatch, (10.0, 2.0, 0.5, 1.0, 6.0, 0.5))
        items_module.update_item_total_cost(cost_env.item_id)
        _patch_cost(monkeypatch, (20.0, 4.0, 1.0, 2.0, 12.0, 1.0))
        items_module.update_item_total_cost(cost_env.item_id)

        cost_ids = {row.id for row in ItemTotalCost.query.all()}
        facts = AnalyticsFact.query.filter_by(fact_type='cost_margin').all()
        assert len(facts) == 2
        assert {f.source_id for f in facts} == cost_ids
        assert {f.cost for f in facts} == {10.0, 20.0}


class TestUpdateItemTotalCostGuards:
    """Bail-out paths must not leave a fact without a cost row."""

    def test_no_fact_when_cost_cannot_be_calculated(self, cost_env, monkeypatch):
        _patch_cost(monkeypatch, (None, 0.0, 0.0, 0.0, 0.0, 0.0))

        items_module.update_item_total_cost(cost_env.item_id)

        assert ItemTotalCost.query.count() == 0
        assert AnalyticsFact.query.filter_by(fact_type='cost_margin').count() == 0

    def test_no_fact_when_cost_is_not_positive(self, cost_env, monkeypatch):
        _patch_cost(monkeypatch, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

        items_module.update_item_total_cost(cost_env.item_id)

        assert ItemTotalCost.query.count() == 0
        assert AnalyticsFact.query.filter_by(fact_type='cost_margin').count() == 0

    def test_no_fact_when_item_belongs_to_another_company(self, cost_env, monkeypatch):
        _patch_cost(monkeypatch)
        monkeypatch.setattr(
            items_module, 'current_user', SimpleNamespace(company_id=cost_env.company_id + 999)
        )

        items_module.update_item_total_cost(cost_env.item_id)

        assert ItemTotalCost.query.count() == 0
        assert AnalyticsFact.query.filter_by(fact_type='cost_margin').count() == 0
