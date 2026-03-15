"""
Multi-Tenant Isolation System for Kodo

This module provides complete tenant isolation, resource quotas, billing tracking,
and data isolation enforcement for secure multi-tenant deployments.

Key Components:
  - TenantContext: Identifies and manages tenant information
  - TenantQuota: Defines and enforces per-tenant resource limits
  - TenantBillingTracker: Tracks costs per tenant with detailed breakdown
  - DataIsolationManager: Enforces strict data separation between tenants
  - MultiTenantOrchestrator: Orchestration aware of tenants and quotas
"""

import uuid
import time
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, List, Any, Set
from datetime import datetime, timedelta
from collections import defaultdict
import threading


class TenantStatus(Enum):
    """Tenant lifecycle status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class QuotaType(Enum):
    """Types of resource quotas."""
    API_CALLS = "api_calls"
    TOKENS = "tokens"
    COMPUTE_HOURS = "compute_hours"
    STORAGE_GB = "storage_gb"
    CONCURRENT_TASKS = "concurrent_tasks"
    MESSAGES = "messages"


class BillingModel(Enum):
    """Billing models supported."""
    PAY_PER_USE = "pay_per_use"
    FLAT_MONTHLY = "flat_monthly"
    TIERED = "tiered"
    RESERVED = "reserved"


@dataclass
class TenantInfo:
    """Comprehensive tenant information."""
    tenant_id: str
    name: str
    owner: str
    created_at: float
    status: TenantStatus = TenantStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "owner": self.owner,
            "created_at": self.created_at,
            "status": self.status.value,
            "metadata": self.metadata,
        }


@dataclass
class TenantQuota:
    """Resource quota for a tenant."""
    tenant_id: str
    quota_type: QuotaType
    limit: float
    reset_period_hours: int = 24
    
    def __init__(
        self,
        tenant_id: str,
        quota_type: QuotaType,
        limit: float,
        reset_period_hours: int = 24,
    ):
        self.tenant_id = tenant_id
        self.quota_type = quota_type
        self.limit = limit
        self.reset_period_hours = reset_period_hours
        self.current_usage = 0.0
        self.last_reset_time = time.time()
    
    def reset_if_needed(self) -> bool:
        """Reset usage if period has elapsed. Returns True if reset."""
        now = time.time()
        elapsed_hours = (now - self.last_reset_time) / 3600
        if elapsed_hours >= self.reset_period_hours:
            self.current_usage = 0.0
            self.last_reset_time = now
            return True
        return False
    
    def can_allocate(self, amount: float) -> bool:
        """Check if amount can be allocated within quota."""
        self.reset_if_needed()
        return (self.current_usage + amount) <= self.limit
    
    def allocate(self, amount: float) -> bool:
        """Attempt to allocate. Returns True if successful."""
        if self.can_allocate(amount):
            self.current_usage += amount
            return True
        return False
    
    def get_remaining(self) -> float:
        """Get remaining quota."""
        self.reset_if_needed()
        return max(0, self.limit - self.current_usage)
    
    def get_usage_percent(self) -> float:
        """Get usage as percentage (0-100)."""
        self.reset_if_needed()
        if self.limit == 0:
            return 0.0
        return (self.current_usage / self.limit) * 100


@dataclass
class BillingEvent:
    """Single billable event."""
    tenant_id: str
    event_type: str
    cost: float
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "cost": self.cost,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass
class TenantBillingRecord:
    """Accumulated billing for a tenant."""
    tenant_id: str
    period_start: float
    period_end: float
    events: List[BillingEvent] = field(default_factory=list)
    total_cost: float = 0.0
    cost_by_type: Dict[str, float] = field(default_factory=dict)
    
    def add_event(self, event: BillingEvent) -> None:
        """Add billing event and update totals."""
        self.events.append(event)
        self.total_cost += event.cost
        self.cost_by_type[event.event_type] = \
            self.cost_by_type.get(event.event_type, 0.0) + event.cost
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_cost": self.total_cost,
            "cost_by_type": self.cost_by_type,
            "event_count": len(self.events),
        }


class TenantContext:
    """Current tenant context for request execution."""
    
    _local = threading.local()
    
    def __init__(self, tenant_id: str, tenant_info: TenantInfo):
        """Initialize tenant context."""
        self.tenant_id = tenant_id
        self.tenant_info = tenant_info
        self.request_id = str(uuid.uuid4())
        self.created_at = time.time()
    
    @classmethod
    def set_current(cls, context: Optional["TenantContext"]) -> None:
        """Set current thread-local context."""
        cls._local.context = context
    
    @classmethod
    def get_current(cls) -> Optional["TenantContext"]:
        """Get current thread-local context."""
        return getattr(cls._local, "context", None)
    
    @classmethod
    def require_context(cls) -> "TenantContext":
        """Get current context or raise error."""
        context = cls.get_current()
        if context is None:
            raise RuntimeError("No tenant context set for current request")
        return context
    
    def __enter__(self):
        """Context manager entry."""
        self.previous = TenantContext.get_current()
        TenantContext.set_current(self)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        TenantContext.set_current(self.previous)


class DataIsolationManager:
    """Enforces strict data isolation between tenants."""
    
    def __init__(self):
        """Initialize data isolation manager."""
        self.access_log: List[Dict[str, Any]] = []
        self.denied_access: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
    
    def verify_tenant_access(self, tenant_id: str, resource_id: str) -> bool:
        """Verify tenant can access resource. Returns False if denied."""
        # Extract tenant from resource_id hash
        try:
            resource_tenant = self._extract_tenant_from_resource(resource_id)
            is_allowed = resource_tenant == tenant_id
            
            with self.lock:
                if is_allowed:
                    self.access_log.append({
                        "tenant_id": tenant_id,
                        "resource_id": resource_id,
                        "timestamp": time.time(),
                        "allowed": True,
                    })
                else:
                    self.denied_access.append({
                        "tenant_id": tenant_id,
                        "resource_id": resource_id,
                        "timestamp": time.time(),
                        "reason": "Tenant mismatch",
                    })
            
            return is_allowed
        except Exception:
            return False
    
    def _extract_tenant_from_resource(self, resource_id: str) -> str:
        """Extract tenant_id from resource_id. Resource IDs are prefixed."""
        parts = resource_id.split(":")
        if len(parts) >= 2:
            return parts[0]
        raise ValueError(f"Invalid resource ID format: {resource_id}")
    
    def create_tenant_resource_id(self, tenant_id: str, resource_name: str) -> str:
        """Create resource ID with tenant isolation."""
        return f"{tenant_id}:{resource_name}"
    
    def get_access_log(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get access log, optionally filtered by tenant."""
        with self.lock:
            if tenant_id:
                return [log for log in self.access_log if log["tenant_id"] == tenant_id]
            return list(self.access_log)
    
    def get_denied_access(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get denied access log, optionally filtered by tenant."""
        with self.lock:
            if tenant_id:
                return [log for log in self.denied_access if log["tenant_id"] == tenant_id]
            return list(self.denied_access)
    
    def get_security_audit(self) -> Dict[str, Any]:
        """Get security audit summary."""
        with self.lock:
            total_access = len(self.access_log)
            total_denied = len(self.denied_access)
            
            return {
                "total_access_attempts": total_access + total_denied,
                "allowed": total_access,
                "denied": total_denied,
                "denial_rate": total_denied / (total_access + total_denied) if (total_access + total_denied) > 0 else 0,
                "access_log_size": total_access,
                "denied_access_size": total_denied,
            }


class TenantBillingTracker:
    """Tracks costs per tenant with detailed breakdown."""
    
    def __init__(self):
        """Initialize billing tracker."""
        self.events: List[BillingEvent] = []
        self.records: Dict[str, List[TenantBillingRecord]] = defaultdict(list)
        self.lock = threading.Lock()
    
    def record_event(
        self,
        tenant_id: str,
        event_type: str,
        cost: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> BillingEvent:
        """Record a billable event."""
        event = BillingEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            cost=cost,
            timestamp=time.time(),
            details=details or {},
        )
        
        with self.lock:
            self.events.append(event)
        
        return event
    
    def get_tenant_costs(
        self,
        tenant_id: str,
        start_time: float,
        end_time: float,
    ) -> Dict[str, Any]:
        """Get costs for tenant in time period."""
        with self.lock:
            tenant_events = [
                e for e in self.events
                if e.tenant_id == tenant_id
                and start_time <= e.timestamp <= end_time
            ]
        
        total_cost = sum(e.cost for e in tenant_events)
        cost_by_type = defaultdict(float)
        for event in tenant_events:
            cost_by_type[event.event_type] += event.cost
        
        return {
            "tenant_id": tenant_id,
            "period_start": start_time,
            "period_end": end_time,
            "total_cost": total_cost,
            "event_count": len(tenant_events),
            "cost_by_type": dict(cost_by_type),
        }
    
    def generate_monthly_billing(self, tenant_id: str, month_offset: int = 0) -> Dict[str, Any]:
        """Generate monthly billing for tenant (0 = current, -1 = last month)."""
        now = datetime.utcnow()
        if month_offset < 0:
            target_date = now + timedelta(days=30 * month_offset)
        else:
            target_date = now
        
        period_start = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_offset >= 0:
            next_month = period_start + timedelta(days=32)
            period_end = next_month.replace(day=1)
        else:
            period_end = period_start + timedelta(days=32)
            period_end = period_end.replace(day=1)
        
        start_ts = period_start.timestamp()
        end_ts = period_end.timestamp()
        
        return self.get_tenant_costs(tenant_id, start_ts, end_ts)
    
    def get_all_tenant_costs(self, start_time: float, end_time: float) -> Dict[str, Dict[str, Any]]:
        """Get costs for all tenants in time period."""
        with self.lock:
            tenant_ids = set(e.tenant_id for e in self.events)
        
        result = {}
        for tenant_id in tenant_ids:
            result[tenant_id] = self.get_tenant_costs(tenant_id, start_time, end_time)
        
        return result
    
    def get_billing_summary(self) -> Dict[str, Any]:
        """Get overall billing summary."""
        with self.lock:
            total_events = len(self.events)
            total_cost = sum(e.cost for e in self.events)
            tenant_count = len(set(e.tenant_id for e in self.events))
            
            cost_by_type = defaultdict(float)
            for event in self.events:
                cost_by_type[event.event_type] += event.cost
        
        return {
            "total_events": total_events,
            "total_cost": total_cost,
            "tenant_count": tenant_count,
            "cost_by_type": dict(cost_by_type),
        }


class TenantManager:
    """Central tenant management system."""
    
    def __init__(self):
        """Initialize tenant manager."""
        self.tenants: Dict[str, TenantInfo] = {}
        self.quotas: Dict[str, List[TenantQuota]] = defaultdict(list)
        self.lock = threading.Lock()
    
    def create_tenant(
        self,
        name: str,
        owner: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TenantInfo:
        """Create a new tenant."""
        tenant_id = str(uuid.uuid4())
        tenant = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            owner=owner,
            created_at=time.time(),
            metadata=metadata or {},
        )
        
        with self.lock:
            self.tenants[tenant_id] = tenant
        
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[TenantInfo]:
        """Get tenant info."""
        with self.lock:
            return self.tenants.get(tenant_id)
    
    def list_tenants(self, status: Optional[TenantStatus] = None) -> List[TenantInfo]:
        """List all tenants, optionally filtered by status."""
        with self.lock:
            tenants = list(self.tenants.values())
        
        if status:
            tenants = [t for t in tenants if t.status == status]
        
        return tenants
    
    def set_tenant_status(self, tenant_id: str, status: TenantStatus) -> bool:
        """Set tenant status."""
        with self.lock:
            if tenant_id not in self.tenants:
                return False
            self.tenants[tenant_id].status = status
            return True
    
    def set_quota(
        self,
        tenant_id: str,
        quota_type: QuotaType,
        limit: float,
        reset_period_hours: int = 24,
    ) -> TenantQuota:
        """Set resource quota for tenant."""
        quota = TenantQuota(
            tenant_id=tenant_id,
            quota_type=quota_type,
            limit=limit,
            reset_period_hours=reset_period_hours,
        )
        
        with self.lock:
            # Remove existing quota of same type
            self.quotas[tenant_id] = [
                q for q in self.quotas[tenant_id]
                if q.quota_type != quota_type
            ]
            self.quotas[tenant_id].append(quota)
        
        return quota
    
    def get_quota(self, tenant_id: str, quota_type: QuotaType) -> Optional[TenantQuota]:
        """Get specific quota for tenant."""
        with self.lock:
            quotas = self.quotas.get(tenant_id, [])
            for quota in quotas:
                if quota.quota_type == quota_type:
                    return quota
        return None
    
    def get_all_quotas(self, tenant_id: str) -> List[TenantQuota]:
        """Get all quotas for tenant."""
        with self.lock:
            return list(self.quotas.get(tenant_id, []))
    
    def check_quota(self, tenant_id: str, quota_type: QuotaType, amount: float) -> bool:
        """Check if quota would allow allocation."""
        quota = self.get_quota(tenant_id, quota_type)
        if quota is None:
            return True  # No quota set = unlimited
        return quota.can_allocate(amount)
    
    def allocate_quota(self, tenant_id: str, quota_type: QuotaType, amount: float) -> bool:
        """Attempt to allocate against quota."""
        quota = self.get_quota(tenant_id, quota_type)
        if quota is None:
            return True  # No quota set = unlimited
        return quota.allocate(amount)


class MultiTenantOrchestrator:
    """Orchestrator aware of tenants and quotas."""
    
    def __init__(
        self,
        tenant_manager: TenantManager,
        billing_tracker: TenantBillingTracker,
        data_isolation: DataIsolationManager,
    ):
        """Initialize multi-tenant orchestrator."""
        self.tenant_manager = tenant_manager
        self.billing_tracker = billing_tracker
        self.data_isolation = data_isolation
        self.task_executions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    def execute_task(
        self,
        tenant_id: str,
        task_id: str,
        cost: float,
        task_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute task with tenant context and quota checking."""
        # Verify tenant exists
        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Unknown tenant: {tenant_id}")
        
        # Check tenant status
        if tenant.status != TenantStatus.ACTIVE:
            raise RuntimeError(f"Tenant {tenant_id} is {tenant.status.value}")
        
        # Check API call quota
        if not self.tenant_manager.allocate_quota(tenant_id, QuotaType.API_CALLS, 1):
            raise RuntimeError(f"API call quota exceeded for tenant {tenant_id}")
        
        # Check cost quota (simplified - would be configurable)
        monthly_limit = 10000.0  # Example limit
        current_month_cost = self._get_current_month_cost(tenant_id)
        if current_month_cost + cost > monthly_limit:
            # Refund the API call
            self.tenant_manager.get_quota(tenant_id, QuotaType.API_CALLS).current_usage -= 1
            raise RuntimeError(f"Monthly cost limit would be exceeded for tenant {tenant_id}")
        
        # Verify data isolation
        resource_id = self.data_isolation.create_tenant_resource_id(tenant_id, task_id)
        if not self.data_isolation.verify_tenant_access(tenant_id, resource_id):
            raise RuntimeError(f"Data isolation violation for tenant {tenant_id}")
        
        # Execute task
        execution_result = {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "resource_id": resource_id,
            "cost": cost,
            "timestamp": time.time(),
            "status": "success",
            "task_data": task_data or {},
        }
        
        with self.lock:
            self.task_executions[resource_id] = execution_result
        
        # Record billing event
        self.billing_tracker.record_event(
            tenant_id=tenant_id,
            event_type="task_execution",
            cost=cost,
            details={
                "task_id": task_id,
                "resource_id": resource_id,
            }
        )
        
        return execution_result
    
    def _get_current_month_cost(self, tenant_id: str) -> float:
        """Get current month cost for tenant."""
        billing = self.billing_tracker.generate_monthly_billing(tenant_id, month_offset=0)
        return billing["total_cost"]
    
    def get_tenant_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive metrics for tenant."""
        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Unknown tenant: {tenant_id}")
        
        quotas = self.tenant_manager.get_all_quotas(tenant_id)
        monthly_cost = self._get_current_month_cost(tenant_id)
        
        return {
            "tenant_info": tenant.to_dict(),
            "quotas": [
                {
                    "type": q.quota_type.value,
                    "limit": q.limit,
                    "current_usage": q.current_usage,
                    "remaining": q.get_remaining(),
                    "usage_percent": q.get_usage_percent(),
                }
                for q in quotas
            ],
            "current_month_cost": monthly_cost,
            "task_count": len([
                e for e in self.task_executions.values()
                if e["tenant_id"] == tenant_id
            ]),
        }
