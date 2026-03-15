"""
Tests for Multi-Tenant Isolation System (Phase 6)

Tests cover:
  - Tenant creation and management
  - Tenant context and isolation
  - Resource quotas and enforcement
  - Billing tracking and accuracy
  - Data isolation verification
  - Security audit functionality
"""

import pytest
import time
import threading
from datetime import datetime, timedelta

from kodo.multi_tenant import (
    TenantInfo,
    TenantStatus,
    TenantContext,
    TenantQuota,
    QuotaType,
    BillingEvent,
    DataIsolationManager,
    TenantBillingTracker,
    TenantManager,
    MultiTenantOrchestrator,
)


class TestTenantInfo:
    """Tests for TenantInfo."""
    
    def test_create_tenant_info(self):
        """Test creating tenant info."""
        info = TenantInfo(
            tenant_id="tenant-1",
            name="Test Tenant",
            owner="owner@example.com",
            created_at=time.time(),
        )
        
        assert info.tenant_id == "tenant-1"
        assert info.name == "Test Tenant"
        assert info.status == TenantStatus.ACTIVE
    
    def test_tenant_info_to_dict(self):
        """Test tenant info serialization."""
        info = TenantInfo(
            tenant_id="tenant-1",
            name="Test Tenant",
            owner="owner@example.com",
            created_at=time.time(),
            metadata={"department": "engineering"},
        )
        
        d = info.to_dict()
        assert d["tenant_id"] == "tenant-1"
        assert d["name"] == "Test Tenant"
        assert d["status"] == "active"
        assert d["metadata"]["department"] == "engineering"


class TestTenantContext:
    """Tests for tenant context management."""
    
    def test_set_and_get_context(self):
        """Test setting and getting tenant context."""
        info = TenantInfo("tenant-1", "Test", "owner", time.time())
        context = TenantContext("tenant-1", info)
        
        TenantContext.set_current(context)
        retrieved = TenantContext.get_current()
        
        assert retrieved is context
        assert retrieved.tenant_id == "tenant-1"
    
    def test_context_manager(self):
        """Test tenant context as context manager."""
        TenantContext.set_current(None)  # Ensure clean state
        info = TenantInfo("tenant-1", "Test", "owner", time.time())
        context = TenantContext("tenant-1", info)
        
        assert TenantContext.get_current() is None
        
        with context:
            assert TenantContext.get_current() is context
        
        assert TenantContext.get_current() is None
    
    def test_nested_contexts(self):
        """Test nested tenant contexts."""
        info1 = TenantInfo("tenant-1", "Test 1", "owner", time.time())
        info2 = TenantInfo("tenant-2", "Test 2", "owner", time.time())
        
        context1 = TenantContext("tenant-1", info1)
        context2 = TenantContext("tenant-2", info2)
        
        with context1:
            assert TenantContext.get_current().tenant_id == "tenant-1"
            
            with context2:
                assert TenantContext.get_current().tenant_id == "tenant-2"
            
            assert TenantContext.get_current().tenant_id == "tenant-1"
    
    def test_require_context(self):
        """Test requiring context with error on missing."""
        TenantContext.set_current(None)
        
        with pytest.raises(RuntimeError, match="No tenant context"):
            TenantContext.require_context()
    
    def test_context_request_id(self):
        """Test context generates unique request ID."""
        info = TenantInfo("tenant-1", "Test", "owner", time.time())
        context1 = TenantContext("tenant-1", info)
        context2 = TenantContext("tenant-1", info)
        
        assert context1.request_id != context2.request_id


class TestTenantQuota:
    """Tests for tenant quotas."""
    
    def test_create_quota(self):
        """Test creating quota."""
        quota = TenantQuota("tenant-1", QuotaType.API_CALLS, 1000)
        
        assert quota.tenant_id == "tenant-1"
        assert quota.quota_type == QuotaType.API_CALLS
        assert quota.limit == 1000
        assert quota.current_usage == 0
    
    def test_allocate_within_quota(self):
        """Test allocating within quota."""
        quota = TenantQuota("tenant-1", QuotaType.API_CALLS, 100)
        
        assert quota.can_allocate(50)
        assert quota.allocate(50)
        assert quota.current_usage == 50
        assert quota.can_allocate(50)
    
    def test_allocate_exceeds_quota(self):
        """Test allocation fails when exceeding quota."""
        quota = TenantQuota("tenant-1", QuotaType.API_CALLS, 100)
        
        assert quota.allocate(100)
        assert not quota.can_allocate(1)
        assert not quota.allocate(1)
    
    def test_get_remaining(self):
        """Test getting remaining quota."""
        quota = TenantQuota("tenant-1", QuotaType.API_CALLS, 100)
        
        assert quota.get_remaining() == 100
        quota.allocate(30)
        assert quota.get_remaining() == 70
    
    def test_get_usage_percent(self):
        """Test usage percentage calculation."""
        quota = TenantQuota("tenant-1", QuotaType.API_CALLS, 100)
        
        assert quota.get_usage_percent() == 0
        quota.allocate(25)
        assert quota.get_usage_percent() == 25
        quota.allocate(25)
        assert quota.get_usage_percent() == 50
    
    def test_quota_reset_period(self):
        """Test quota resets after period."""
        quota = TenantQuota(
            "tenant-1",
            QuotaType.API_CALLS,
            100,
            reset_period_hours=0.001  # Very short for testing
        )
        
        quota.allocate(100)
        assert quota.current_usage == 100
        
        # Manual reset (normally by elapsed time)
        quota.last_reset_time = time.time() - 10  # 10 seconds ago
        quota.reset_if_needed()
        assert quota.current_usage == 0


class TestDataIsolationManager:
    """Tests for data isolation enforcement."""
    
    def test_create_tenant_resource_id(self):
        """Test creating resource ID with tenant prefix."""
        manager = DataIsolationManager()
        
        resource_id = manager.create_tenant_resource_id("tenant-1", "task-123")
        assert resource_id == "tenant-1:task-123"
    
    def test_verify_valid_access(self):
        """Test verifying valid tenant access."""
        manager = DataIsolationManager()
        resource_id = manager.create_tenant_resource_id("tenant-1", "task-123")
        
        assert manager.verify_tenant_access("tenant-1", resource_id)
    
    def test_verify_denied_access(self):
        """Test denying cross-tenant access."""
        manager = DataIsolationManager()
        resource_id = manager.create_tenant_resource_id("tenant-1", "task-123")
        
        assert not manager.verify_tenant_access("tenant-2", resource_id)
    
    def test_access_logging(self):
        """Test logging of access attempts."""
        manager = DataIsolationManager()
        resource_id = manager.create_tenant_resource_id("tenant-1", "task-123")
        
        manager.verify_tenant_access("tenant-1", resource_id)
        manager.verify_tenant_access("tenant-2", resource_id)
        
        access_log = manager.get_access_log()
        denied_log = manager.get_denied_access()
        
        assert len(access_log) == 1
        assert len(denied_log) == 1
    
    def test_access_log_filtering(self):
        """Test filtering access logs by tenant."""
        manager = DataIsolationManager()
        resource1 = manager.create_tenant_resource_id("tenant-1", "task-1")
        resource2 = manager.create_tenant_resource_id("tenant-2", "task-2")
        
        manager.verify_tenant_access("tenant-1", resource1)
        manager.verify_tenant_access("tenant-2", resource2)
        
        tenant1_logs = manager.get_access_log("tenant-1")
        assert len(tenant1_logs) == 1
        assert tenant1_logs[0]["tenant_id"] == "tenant-1"
    
    def test_security_audit(self):
        """Test security audit summary."""
        manager = DataIsolationManager()
        resource_id = manager.create_tenant_resource_id("tenant-1", "task-1")
        
        # 3 allowed, 2 denied
        manager.verify_tenant_access("tenant-1", resource_id)
        manager.verify_tenant_access("tenant-1", resource_id)
        manager.verify_tenant_access("tenant-1", resource_id)
        manager.verify_tenant_access("tenant-2", resource_id)
        manager.verify_tenant_access("tenant-2", resource_id)
        
        audit = manager.get_security_audit()
        assert audit["total_access_attempts"] == 5
        assert audit["allowed"] == 3
        assert audit["denied"] == 2
        assert audit["denial_rate"] == 0.4


class TestBillingEvent:
    """Tests for billing events."""
    
    def test_create_billing_event(self):
        """Test creating billing event."""
        event = BillingEvent(
            tenant_id="tenant-1",
            event_type="api_call",
            cost=0.05,
            timestamp=time.time(),
        )
        
        assert event.tenant_id == "tenant-1"
        assert event.cost == 0.05
    
    def test_billing_event_serialization(self):
        """Test billing event to dict."""
        event = BillingEvent(
            tenant_id="tenant-1",
            event_type="api_call",
            cost=0.05,
            timestamp=time.time(),
            details={"api": "gpt-4"},
        )
        
        d = event.to_dict()
        assert d["tenant_id"] == "tenant-1"
        assert d["event_type"] == "api_call"
        assert d["cost"] == 0.05
        assert d["details"]["api"] == "gpt-4"


class TestTenantBillingTracker:
    """Tests for billing tracking."""
    
    def test_record_event(self):
        """Test recording billing event."""
        tracker = TenantBillingTracker()
        
        event = tracker.record_event(
            "tenant-1",
            "api_call",
            0.10,
            {"model": "gpt-4"}
        )
        
        assert event.tenant_id == "tenant-1"
        assert event.cost == 0.10
    
    def test_get_tenant_costs(self):
        """Test getting costs for tenant."""
        tracker = TenantBillingTracker()
        
        now = time.time()
        tracker.record_event("tenant-1", "api_call", 0.10)
        tracker.record_event("tenant-1", "storage", 0.05)
        tracker.record_event("tenant-2", "api_call", 0.15)
        
        costs = tracker.get_tenant_costs("tenant-1", now - 100, now + 100)
        
        assert costs["total_cost"] == pytest.approx(0.15)
        assert costs["event_count"] == 2
        assert costs["cost_by_type"]["api_call"] == pytest.approx(0.10)
        assert costs["cost_by_type"]["storage"] == pytest.approx(0.05)
    
    def test_get_all_tenant_costs(self):
        """Test getting costs for all tenants."""
        tracker = TenantBillingTracker()
        
        now = time.time()
        tracker.record_event("tenant-1", "api_call", 0.10)
        tracker.record_event("tenant-2", "api_call", 0.20)
        
        all_costs = tracker.get_all_tenant_costs(now - 100, now + 100)
        
        assert "tenant-1" in all_costs
        assert "tenant-2" in all_costs
        assert all_costs["tenant-1"]["total_cost"] == 0.10
        assert all_costs["tenant-2"]["total_cost"] == 0.20
    
    def test_billing_summary(self):
        """Test billing summary."""
        tracker = TenantBillingTracker()
        
        tracker.record_event("tenant-1", "api_call", 0.10)
        tracker.record_event("tenant-1", "storage", 0.05)
        tracker.record_event("tenant-2", "api_call", 0.20)
        
        summary = tracker.get_billing_summary()
        
        assert summary["total_events"] == 3
        assert summary["total_cost"] == pytest.approx(0.35)
        assert summary["tenant_count"] == 2
        assert summary["cost_by_type"]["api_call"] == pytest.approx(0.30)


class TestTenantManager:
    """Tests for tenant management."""
    
    def test_create_tenant(self):
        """Test creating tenant."""
        manager = TenantManager()
        
        tenant = manager.create_tenant(
            "Test Org",
            "owner@example.com",
            {"department": "engineering"}
        )
        
        assert tenant.name == "Test Org"
        assert tenant.status == TenantStatus.ACTIVE
    
    def test_get_tenant(self):
        """Test getting tenant."""
        manager = TenantManager()
        
        created = manager.create_tenant("Test", "owner@example.com")
        retrieved = manager.get_tenant(created.tenant_id)
        
        assert retrieved is not None
        assert retrieved.tenant_id == created.tenant_id
    
    def test_list_tenants(self):
        """Test listing tenants."""
        manager = TenantManager()
        
        t1 = manager.create_tenant("Tenant 1", "owner1@example.com")
        t2 = manager.create_tenant("Tenant 2", "owner2@example.com")
        
        tenants = manager.list_tenants()
        assert len(tenants) == 2
    
    def test_set_tenant_status(self):
        """Test setting tenant status."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        assert manager.set_tenant_status(tenant.tenant_id, TenantStatus.SUSPENDED)
        
        updated = manager.get_tenant(tenant.tenant_id)
        assert updated.status == TenantStatus.SUSPENDED
    
    def test_set_quota(self):
        """Test setting resource quota."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        quota = manager.set_quota(
            tenant.tenant_id,
            QuotaType.API_CALLS,
            1000
        )
        
        assert quota.limit == 1000
    
    def test_get_quota(self):
        """Test getting quota."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        manager.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 1000)
        
        quota = manager.get_quota(tenant.tenant_id, QuotaType.API_CALLS)
        assert quota is not None
        assert quota.limit == 1000
    
    def test_get_all_quotas(self):
        """Test getting all quotas for tenant."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        manager.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 1000)
        manager.set_quota(tenant.tenant_id, QuotaType.TOKENS, 100000)
        
        quotas = manager.get_all_quotas(tenant.tenant_id)
        assert len(quotas) == 2
    
    def test_check_quota(self):
        """Test checking quota."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        manager.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
        
        assert manager.check_quota(tenant.tenant_id, QuotaType.API_CALLS, 50)
        assert manager.check_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
        assert not manager.check_quota(tenant.tenant_id, QuotaType.API_CALLS, 101)
    
    def test_allocate_quota(self):
        """Test allocating quota."""
        manager = TenantManager()
        
        tenant = manager.create_tenant("Test", "owner@example.com")
        manager.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
        
        assert manager.allocate_quota(tenant.tenant_id, QuotaType.API_CALLS, 50)
        assert manager.allocate_quota(tenant.tenant_id, QuotaType.API_CALLS, 50)
        assert not manager.allocate_quota(tenant.tenant_id, QuotaType.API_CALLS, 1)


class TestMultiTenantOrchestrator:
    """Tests for multi-tenant orchestrator."""
    
    def test_execute_task_success(self):
        """Test successful task execution."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        tenant = tenant_mgr.create_tenant("Test", "owner@example.com")
        tenant_mgr.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 1000)
        
        result = orchestrator.execute_task(
            tenant.tenant_id,
            "task-1",
            0.10,
            {"data": "test"}
        )
        
        assert result["status"] == "success"
        assert result["cost"] == 0.10
        assert result["tenant_id"] == tenant.tenant_id
    
    def test_execute_task_unknown_tenant(self):
        """Test task execution fails for unknown tenant."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        with pytest.raises(ValueError, match="Unknown tenant"):
            orchestrator.execute_task("unknown", "task-1", 0.10)
    
    def test_execute_task_suspended_tenant(self):
        """Test task execution fails for suspended tenant."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        tenant = tenant_mgr.create_tenant("Test", "owner@example.com")
        tenant_mgr.set_tenant_status(tenant.tenant_id, TenantStatus.SUSPENDED)
        
        with pytest.raises(RuntimeError, match="suspended"):
            orchestrator.execute_task(tenant.tenant_id, "task-1", 0.10)
    
    def test_execute_task_quota_exceeded(self):
        """Test task execution fails when quota exceeded."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        tenant = tenant_mgr.create_tenant("Test", "owner@example.com")
        tenant_mgr.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 1)
        
        orchestrator.execute_task(tenant.tenant_id, "task-1", 0.10)
        
        with pytest.raises(RuntimeError, match="quota exceeded"):
            orchestrator.execute_task(tenant.tenant_id, "task-2", 0.10)
    
    def test_execute_multiple_tasks(self):
        """Test executing multiple tasks."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        tenant = tenant_mgr.create_tenant("Test", "owner@example.com")
        tenant_mgr.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 10)
        
        for i in range(5):
            result = orchestrator.execute_task(
                tenant.tenant_id,
                f"task-{i}",
                0.10 * (i + 1)
            )
            assert result["status"] == "success"
    
    def test_task_data_isolation(self):
        """Test that task data is isolated between tenants."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        t1 = tenant_mgr.create_tenant("Tenant 1", "owner1@example.com")
        t2 = tenant_mgr.create_tenant("Tenant 2", "owner2@example.com")
        
        tenant_mgr.set_quota(t1.tenant_id, QuotaType.API_CALLS, 10)
        tenant_mgr.set_quota(t2.tenant_id, QuotaType.API_CALLS, 10)
        
        r1 = orchestrator.execute_task(t1.tenant_id, "task-1", 0.10)
        r2 = orchestrator.execute_task(t2.tenant_id, "task-2", 0.10)
        
        # Verify isolation - each task has tenant-specific resource ID
        assert r1["resource_id"].startswith(t1.tenant_id)
        assert r2["resource_id"].startswith(t2.tenant_id)
        assert r1["resource_id"] != r2["resource_id"]
    
    def test_get_tenant_metrics(self):
        """Test getting comprehensive tenant metrics."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        tenant = tenant_mgr.create_tenant("Test", "owner@example.com")
        tenant_mgr.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
        
        orchestrator.execute_task(tenant.tenant_id, "task-1", 0.10)
        
        metrics = orchestrator.get_tenant_metrics(tenant.tenant_id)
        
        assert metrics["tenant_info"]["tenant_id"] == tenant.tenant_id
        assert metrics["task_count"] == 1
        assert metrics["current_month_cost"] > 0
        assert len(metrics["quotas"]) == 1


class TestMultiTenantIntegration:
    """Integration tests for multi-tenant system."""
    
    def test_complete_workflow(self):
        """Test complete multi-tenant workflow."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        # Create two tenants
        t1 = tenant_mgr.create_tenant("Org 1", "admin1@example.com", {"region": "us"})
        t2 = tenant_mgr.create_tenant("Org 2", "admin2@example.com", {"region": "eu"})
        
        # Set quotas
        for tenant in [t1, t2]:
            tenant_mgr.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
            tenant_mgr.set_quota(tenant.tenant_id, QuotaType.TOKENS, 100000)
        
        # Execute tasks
        for i in range(3):
            orchestrator.execute_task(t1.tenant_id, f"t1-task-{i}", 0.05)
            orchestrator.execute_task(t2.tenant_id, f"t2-task-{i}", 0.10)
        
        # Verify costs
        billing1 = billing.generate_monthly_billing(t1.tenant_id)
        billing2 = billing.generate_monthly_billing(t2.tenant_id)
        
        assert billing1["total_cost"] == pytest.approx(0.15)
        assert billing2["total_cost"] == pytest.approx(0.30)
        assert billing1["event_count"] == 3
        assert billing2["event_count"] == 3
        
        # Verify metrics
        metrics1 = orchestrator.get_tenant_metrics(t1.tenant_id)
        metrics2 = orchestrator.get_tenant_metrics(t2.tenant_id)
        
        assert metrics1["task_count"] == 3
        assert metrics2["task_count"] == 3
    
    def test_security_audit_integration(self):
        """Test security audit across multiple tenants."""
        tenant_mgr = TenantManager()
        billing = TenantBillingTracker()
        isolation = DataIsolationManager()
        orchestrator = MultiTenantOrchestrator(tenant_mgr, billing, isolation)
        
        t1 = tenant_mgr.create_tenant("Org 1", "admin@example.com")
        t2 = tenant_mgr.create_tenant("Org 2", "admin@example.com")
        
        tenant_mgr.set_quota(t1.tenant_id, QuotaType.API_CALLS, 10)
        tenant_mgr.set_quota(t2.tenant_id, QuotaType.API_CALLS, 10)
        
        # Execute tasks (legitimate access)
        orchestrator.execute_task(t1.tenant_id, "task-1", 0.05)
        orchestrator.execute_task(t2.tenant_id, "task-2", 0.05)
        
        # Attempt cross-tenant access (should fail)
        resource_t1 = isolation.create_tenant_resource_id(t1.tenant_id, "task-1")
        isolation.verify_tenant_access(t2.tenant_id, resource_t1)  # Should be denied
        
        # Check audit
        audit = isolation.get_security_audit()
        assert audit["allowed"] == 2  # Two legitimate accesses
        assert audit["denied"] == 1   # One denied access
        assert audit["denial_rate"] == 1/3


class TestThreadSafety:
    """Tests for thread safety of multi-tenant system."""
    
    def test_concurrent_tenant_creation(self):
        """Test concurrent tenant creation."""
        manager = TenantManager()
        tenants = []
        
        def create_tenants():
            for i in range(10):
                t = manager.create_tenant(f"Org {i}", f"owner{i}@example.com")
                tenants.append(t)
        
        threads = [threading.Thread(target=create_tenants) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        all_tenants = manager.list_tenants()
        assert len(all_tenants) == 30  # 3 threads * 10 tenants
    
    def test_concurrent_quota_allocation(self):
        """Test concurrent quota allocation."""
        manager = TenantManager()
        tenant = manager.create_tenant("Test", "owner@example.com")
        manager.set_quota(tenant.tenant_id, QuotaType.API_CALLS, 100)
        
        results = []
        
        def allocate_quota():
            for _ in range(20):
                result = manager.allocate_quota(tenant.tenant_id, QuotaType.API_CALLS, 1)
                results.append(result)
        
        threads = [threading.Thread(target=allocate_quota) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # 5 threads * 20 = 100 total attempts, 100 succeed, rest fail
        assert results.count(True) == 100
        assert results.count(False) == 0  # Exactly 100 units, all allocated
    
    def test_concurrent_billing_events(self):
        """Test concurrent billing event recording."""
        tracker = TenantBillingTracker()
        
        def record_events(tenant_id):
            for i in range(50):
                tracker.record_event(tenant_id, "api_call", 0.01)
        
        threads = [
            threading.Thread(target=record_events, args=(f"tenant-{i}",))
            for i in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        summary = tracker.get_billing_summary()
        assert summary["total_events"] == 250  # 5 tenants * 50 events
        assert summary["tenant_count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
