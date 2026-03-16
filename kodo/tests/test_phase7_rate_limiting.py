"""
Phase 7: Rate Limiting & Throttling Tests

Comprehensive tests for distributed rate limiting with multiple algorithms:
- Token bucket algorithm
- Sliding window algorithm
- Leaky bucket algorithm
- Adaptive rate limiting
- Rate limit manager and multi-key support
"""

import pytest
import time
import asyncio
from anyio import from_thread, to_thread
from src.rate_limiting import (
    RateLimitQuota,
    RateLimitAlgorithm,
    RateLimitStatus,
    RateLimitResult,
    TokenBucketLimiter,
    SlidingWindowLimiter,
    LeakyBucketLimiter,
    AdaptiveRateLimiter,
    RateLimitManager,
)


# Use anyio for async test support
pytestmark = pytest.mark.anyio


class TestRateLimitQuota:
    """Test rate limit quota configuration"""
    
    def test_quota_creation_valid(self):
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=1000)
        assert quota.requests_per_second == 100.0
        assert quota.burst_size == 1000
        assert quota.window_size_seconds == 60
    
    def test_quota_custom_window(self):
        quota = RateLimitQuota(
            requests_per_second=50.0,
            burst_size=500,
            window_size_seconds=30
        )
        assert quota.window_size_seconds == 30
    
    def test_quota_invalid_rps(self):
        with pytest.raises(ValueError):
            RateLimitQuota(requests_per_second=0, burst_size=100)
        
        with pytest.raises(ValueError):
            RateLimitQuota(requests_per_second=-10, burst_size=100)
    
    def test_quota_invalid_burst(self):
        with pytest.raises(ValueError):
            RateLimitQuota(requests_per_second=100, burst_size=0)
        
        with pytest.raises(ValueError):
            RateLimitQuota(requests_per_second=100, burst_size=-50)


class TestTokenBucketLimiter:
    """Test token bucket rate limiting algorithm"""
    
    
    async def test_allowed_request(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=100)
        limiter = TokenBucketLimiter(quota)
        
        result = await limiter.check(1)
        assert result.allowed is True
        assert result.status == RateLimitStatus.ALLOWED
        assert result.remaining_requests > 0
    
    
    async def test_burst_limit(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=5)
        limiter = TokenBucketLimiter(quota)
        
        # Use up burst
        for _ in range(5):
            result = await limiter.check(1)
            assert result.allowed is True
        
        # Next request should fail (no refill time)
        result = await limiter.check(1)
        assert result.allowed is False
        assert result.status == RateLimitStatus.RATE_LIMITED
        assert result.retry_after_seconds is not None
    
    
    async def test_token_refill(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=10)
        limiter = TokenBucketLimiter(quota)
        
        # Use all tokens
        for _ in range(10):
            await limiter.check(1)
        
        # Wait for refill
        await asyncio.sleep(0.2)  # 10 RPS = 2 tokens in 0.2 seconds
        
        result = await limiter.check(1)
        assert result.allowed is True
    
    
    async def test_multi_token_request(self):
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        limiter = TokenBucketLimiter(quota)
        
        result = await limiter.check(50)
        assert result.allowed is True
        assert result.remaining_requests == 50
    
    
    async def test_retry_after_calculation(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=5)
        limiter = TokenBucketLimiter(quota)
        
        # Use up burst
        for _ in range(5):
            await limiter.check(1)
        
        # Check retry time
        result = await limiter.check(1)
        assert result.allowed is False
        assert result.retry_after_seconds > 0
        assert result.retry_after_seconds < 1.0  # Should be < 0.1 seconds


class TestSlidingWindowLimiter:
    """Test sliding window rate limiting algorithm"""
    
    
    async def test_allowed_request(self):
        quota = RateLimitQuota(
            requests_per_second=10.0,
            burst_size=100,
            window_size_seconds=60
        )
        limiter = SlidingWindowLimiter(quota)
        
        result = await limiter.check(1)
        assert result.allowed is True
        assert result.status == RateLimitStatus.ALLOWED
    
    
    async def test_window_capacity(self):
        quota = RateLimitQuota(
            requests_per_second=10.0,
            burst_size=100,
            window_size_seconds=1
        )
        limiter = SlidingWindowLimiter(quota)
        
        # 10 RPS * 1 second = 10 max requests
        for _ in range(10):
            result = await limiter.check(1)
            assert result.allowed is True
        
        # 11th should fail
        result = await limiter.check(1)
        assert result.allowed is False
    
    
    async def test_window_expiry(self):
        quota = RateLimitQuota(
            requests_per_second=10.0,
            burst_size=100,
            window_size_seconds=1
        )
        limiter = SlidingWindowLimiter(quota)
        
        # Fill window
        for _ in range(10):
            await limiter.check(1)
        
        # Should fail
        result = await limiter.check(1)
        assert result.allowed is False
        
        # Wait for window to expire
        await asyncio.sleep(1.1)
        
        # Should succeed again
        result = await limiter.check(1)
        assert result.allowed is True


class TestLeakyBucketLimiter:
    """Test leaky bucket rate limiting algorithm"""
    
    
    async def test_allowed_request(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=50)
        limiter = LeakyBucketLimiter(quota)
        
        result = await limiter.check(1)
        assert result.allowed is True
        assert result.status == RateLimitStatus.ALLOWED
    
    
    async def test_bucket_overflow(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=5)
        limiter = LeakyBucketLimiter(quota)
        
        # Fill bucket
        for _ in range(5):
            result = await limiter.check(1)
            assert result.allowed is True
        
        # Next request overflows
        result = await limiter.check(1)
        assert result.allowed is False
        assert result.retry_after_seconds > 0
    
    
    async def test_leak_over_time(self):
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=10)
        limiter = LeakyBucketLimiter(quota)
        
        # Fill bucket
        for _ in range(10):
            await limiter.check(1)
        
        # Should fail
        result = await limiter.check(1)
        assert result.allowed is False
        
        # Wait for leak
        await asyncio.sleep(0.2)  # 10 RPS = 2 tokens leak in 0.2 seconds
        
        # Should now succeed
        result = await limiter.check(1)
        assert result.allowed is True


class TestAdaptiveRateLimiter:
    """Test adaptive rate limiting with load adjustment"""
    
    
    async def test_base_quota_no_load(self):
        base_quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        limiter = AdaptiveRateLimiter(base_quota)
        
        result = await limiter.check(1)
        assert result.allowed is True
        assert result.limit_info["system_load"] == 0.0
    
    
    async def test_quota_reduction_high_load(self):
        base_quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        limiter = AdaptiveRateLimiter(base_quota, min_load_reduction=0.5)
        
        # Set high load
        await limiter.set_system_load(1.0)
        
        # Should have 50% reduction
        assert limiter.current_quota.requests_per_second == 50.0
        assert limiter.current_quota.burst_size == 50
    
    
    async def test_partial_load(self):
        base_quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        limiter = AdaptiveRateLimiter(base_quota, min_load_reduction=0.5)
        
        # Set 50% load
        await limiter.set_system_load(0.5)
        
        # Should have 25% reduction
        assert limiter.current_quota.requests_per_second == 75.0
        assert limiter.current_quota.burst_size == 75
    
    
    async def test_load_bounds(self):
        base_quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        limiter = AdaptiveRateLimiter(base_quota)
        
        # Test negative load clamped to 0
        await limiter.set_system_load(-1.0)
        assert limiter.system_load == 0.0
        
        # Test > 1.0 clamped to 1.0
        await limiter.set_system_load(2.0)
        assert limiter.system_load == 1.0


class TestRateLimitManager:
    """Test centralized rate limit manager"""
    
    
    async def test_configure_limiter(self):
        manager = RateLimitManager(RateLimitAlgorithm.TOKEN_BUCKET)
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        await manager.configure_limiter("tenant-1", quota)
        
        assert "tenant-1" in manager.limiters
        assert "tenant-1" in manager.quotas
    
    
    async def test_multiple_limiters(self):
        manager = RateLimitManager()
        quota1 = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        quota2 = RateLimitQuota(requests_per_second=50.0, burst_size=50)
        
        await manager.configure_limiter("tenant-1", quota1)
        await manager.configure_limiter("tenant-2", quota2)
        
        assert len(manager.limiters) == 2
    
    
    async def test_check_limit_configured_key(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        await manager.configure_limiter("tenant-1", quota)
        result = await manager.check_limit("tenant-1", 1)
        
        assert result.allowed is True
        assert result.status == RateLimitStatus.ALLOWED
    
    
    async def test_auto_configure_on_check(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        result = await manager.check_limit("new-tenant", 1, quota=quota)
        assert result.allowed is True
        assert "new-tenant" in manager.limiters
    
    
    async def test_unconfigured_key_fails(self):
        manager = RateLimitManager()
        
        result = await manager.check_limit("unknown-tenant", 1)
        assert result.allowed is False
        assert result.status == RateLimitStatus.QUOTA_EXCEEDED
    
    
    async def test_track_denied_requests(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=10.0, burst_size=2)
        
        await manager.configure_limiter("tenant-1", quota)
        
        # Use up burst
        for _ in range(2):
            await manager.check_limit("tenant-1", 1)
        
        # This should be denied
        result = await manager.check_limit("tenant-1", 1)
        assert result.allowed is False
        
        # Check denial tracking
        assert len(manager.denied_requests) > 0
    
    
    async def test_get_stats(self):
        manager = RateLimitManager(RateLimitAlgorithm.TOKEN_BUCKET)
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        await manager.configure_limiter("tenant-1", quota)
        
        stats = await manager.get_stats("tenant-1")
        assert "quota" in stats
        assert "algorithm" in stats
        assert stats["algorithm"] == "token_bucket"
    
    
    async def test_get_stats_all(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        await manager.configure_limiter("tenant-1", quota)
        await manager.configure_limiter("tenant-2", quota)
        
        stats = await manager.get_stats()
        assert stats["total_limiters"] == 2
        assert len(stats["limiters"]) == 2
    
    
    async def test_export_metrics(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        await manager.configure_limiter("tenant-1", quota)
        metrics = manager.export_metrics()
        
        assert "total_limiters" in metrics
        assert "total_denied_requests" in metrics
        assert "algorithm" in metrics


class TestMultiTenantRateLimiting:
    """Test rate limiting with multiple tenants"""
    
    
    async def test_independent_tenant_limits(self):
        manager = RateLimitManager()
        quota1 = RateLimitQuota(requests_per_second=10.0, burst_size=5)
        quota2 = RateLimitQuota(requests_per_second=20.0, burst_size=10)
        
        await manager.configure_limiter("tenant-1", quota1)
        await manager.configure_limiter("tenant-2", quota2)
        
        # Tenant 1: fill burst (5)
        for _ in range(5):
            await manager.check_limit("tenant-1", 1)
        
        # Tenant 1: should fail
        result1 = await manager.check_limit("tenant-1", 1)
        assert result1.allowed is False
        
        # Tenant 2: should still have capacity
        result2 = await manager.check_limit("tenant-2", 1)
        assert result2.allowed is True
    
    
    async def test_tenant_isolation(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=5.0, burst_size=3)
        
        await manager.configure_limiter("tenant-1", quota)
        await manager.configure_limiter("tenant-2", quota)
        
        # Both use their burst independently
        for _ in range(3):
            result1 = await manager.check_limit("tenant-1", 1)
            result2 = await manager.check_limit("tenant-2", 1)
            assert result1.allowed is True
            assert result2.allowed is True
        
        # Both should now be rate limited
        result1 = await manager.check_limit("tenant-1", 1)
        result2 = await manager.check_limit("tenant-2", 1)
        assert result1.allowed is False
        assert result2.allowed is False


class TestRateLimitPerformance:
    """Test performance characteristics"""
    
    
    async def test_large_number_of_limiters(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=100)
        
        # Create 1000 limiters
        for i in range(1000):
            await manager.configure_limiter(f"tenant-{i}", quota)
        
        assert len(manager.limiters) == 1000
        
        # Random check should still be fast
        start = time.time()
        for i in range(0, 1000, 100):
            await manager.check_limit(f"tenant-{i}", 1)
        elapsed = time.time() - start
        
        # Should complete in under 100ms
        assert elapsed < 0.1
    
    
    async def test_concurrent_checks(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=1000.0, burst_size=1000)
        
        await manager.configure_limiter("tenant-1", quota)
        
        # Run 100 concurrent checks
        tasks = [
            manager.check_limit("tenant-1", 1)
            for _ in range(100)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed (high limit)
        assert all(r.allowed for r in results)
    
    
    async def test_concurrent_rate_limiting(self):
        manager = RateLimitManager()
        quota = RateLimitQuota(requests_per_second=100.0, burst_size=10)
        
        await manager.configure_limiter("tenant-1", quota)
        
        # Run concurrent checks that hit the limit
        tasks = [
            manager.check_limit("tenant-1", 1)
            for _ in range(50)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Some should be allowed, some denied
        allowed = sum(1 for r in results if r.allowed)
        denied = sum(1 for r in results if not r.allowed)
        
        assert allowed > 0
        assert denied > 0
        assert allowed + denied == 50


class TestRateLimitResult:
    """Test rate limit result objects"""
    
    def test_result_to_dict(self):
        result = RateLimitResult(
            status=RateLimitStatus.ALLOWED,
            allowed=True,
            remaining_requests=50,
            retry_after_seconds=None,
            limit_info={"test": "value"}
        )
        
        result_dict = result.to_dict()
        assert result_dict["status"] == "allowed"
        assert result_dict["allowed"] is True
        assert result_dict["remaining_requests"] == 50
        assert result_dict["limit_info"]["test"] == "value"
    
    def test_result_with_retry(self):
        result = RateLimitResult(
            status=RateLimitStatus.RATE_LIMITED,
            allowed=False,
            remaining_requests=0,
            retry_after_seconds=2.5
        )
        
        assert result.retry_after_seconds == 2.5
        assert not result.allowed
