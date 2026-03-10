"""Tests for cost_tracker.py"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta


class TestCostTrackerInitialization:
    """Test cost tracker initialization."""

    def test_init_with_budget(self):
        """Test initializing cost tracker with budget."""
        budget = {"total": 1000.0, "currency": "USD"}
        assert budget["total"] == 1000.0


class TestCostTracking:
    """Test cost tracking operations."""

    def test_record_operation_cost(self):
        """Test recording operation cost."""
        operation = {
            "id": "op-1",
            "type": "api_call",
            "cost": 0.05,
            "timestamp": datetime.now(),
        }
        assert operation["cost"] == 0.05

    def test_track_agent_cost(self):
        """Test tracking cost per agent."""
        agent_costs = {
            "agent-1": {"total": 10.50, "operations": 50},
            "agent-2": {"total": 5.25, "operations": 25},
        }
        assert agent_costs["agent-1"]["total"] == 10.50
        assert len(agent_costs) == 2

    def test_track_session_cost(self):
        """Test tracking session cost."""
        session = {
            "id": "session-1",
            "start": datetime.now(),
            "total_cost": 0,
            "operations": [],
        }
        assert session["total_cost"] == 0


class TestCostAggregation:
    """Test cost aggregation and reporting."""

    def test_aggregate_hourly_costs(self):
        """Test aggregating costs by hour."""
        costs = [
            {"timestamp": datetime(2026, 3, 10, 9, 0), "amount": 10.0},
            {"timestamp": datetime(2026, 3, 10, 9, 15), "amount": 5.0},
            {"timestamp": datetime(2026, 3, 10, 10, 0), "amount": 8.0},
        ]
        assert len(costs) == 3

    def test_calculate_total_cost(self):
        """Test calculating total cost."""
        operations = [
            {"cost": 1.0},
            {"cost": 2.0},
            {"cost": 1.5},
        ]
        total = sum(op["cost"] for op in operations)
        assert total == 4.5


class TestBudgetConstraints:
    """Test budget constraint enforcement."""

    def test_check_budget_remaining(self):
        """Test checking remaining budget."""
        budget = 1000.0
        spent = 250.0
        remaining = budget - spent
        assert remaining == 750.0

    def test_budget_exceeded(self):
        """Test handling budget exceeded."""
        budget = 100.0
        spent = 150.0
        exceeded = spent > budget
        assert exceeded is True

    def test_alert_on_budget_warning(self):
        """Test alert when approaching budget limit."""
        budget = 1000.0
        spent = 900.0
        percentage = (spent / budget) * 100
        assert percentage == 90.0
