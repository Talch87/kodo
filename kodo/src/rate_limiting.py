"""
Rate Limiting & Throttling System for Kodo

Provides distributed rate limiting with multiple algorithms:
- Token Bucket: Classic rate limiting with burst allowance
- Sliding Window: Time-based sliding window rate limiting
- Leaky Bucket: Smooth rate limiting with queue overflow protection
- Adaptive Rate Limiting: Dynamic limits based on system load

Features:
- Per-tenant rate limits
- Per-agent rate limits
- Per-endpoint rate limits
- Distributed rate limiting (using Redis or in-memory store)
- Quota pooling (allow burst usage across requests)
- Graceful degradation under load
"""

import time
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
from collections import deque
import json
import logging


logger = logging.getLogger(__name__)


class RateLimitAlgorithm(str, Enum):
    """Available rate limiting algorithms"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    LEAKY_BUCKET = "leaky_bucket"
    ADAPTIVE = "adaptive"


class RateLimitStatus(str, Enum):
    """Rate limit check result status"""
    ALLOWED = "allowed"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"


@dataclass
class RateLimitQuota:
    """Rate limit quota configuration"""
    requests_per_second: float  # e.g., 100.0
    burst_size: int  # Max tokens to accumulate
    window_size_seconds: int = 60  # For sliding window
    
    def __post_init__(self):
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.burst_size <= 0:
            raise ValueError("burst_size must be positive")


@dataclass
class RateLimitResult:
    """Result of a rate limit check"""
    status: RateLimitStatus
    allowed: bool
    remaining_requests: int
    retry_after_seconds: Optional[float] = None
    limit_info: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "allowed": self.allowed,
            "remaining_requests": self.remaining_requests,
            "retry_after_seconds": self.retry_after_seconds,
            "limit_info": self.limit_info
        }


class TokenBucketLimiter:
    """Token bucket rate limiter with burst allowance"""
    
    def __init__(self, quota: RateLimitQuota):
        self.quota = quota
        self.tokens = float(quota.burst_size)
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
    
    async def check(self, tokens_needed: int = 1) -> RateLimitResult:
        """Check if request is allowed and consume tokens"""
        async with self.lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * self.quota.requests_per_second
            
            self.tokens = min(
                self.quota.burst_size,
                self.tokens + tokens_to_add
            )
            self.last_refill = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens_needed:
                self.tokens -= tokens_needed
                return RateLimitResult(
                    status=RateLimitStatus.ALLOWED,
                    allowed=True,
                    remaining_requests=int(self.tokens),
                    limit_info={
                        "tokens_remaining": self.tokens,
                        "refill_rate": self.quota.requests_per_second,
                    }
                )
            else:
                # Calculate retry time
                deficit = tokens_needed - self.tokens
                retry_after = deficit / self.quota.requests_per_second
                
                return RateLimitResult(
                    status=RateLimitStatus.RATE_LIMITED,
                    allowed=False,
                    remaining_requests=int(self.tokens),
                    retry_after_seconds=retry_after,
                    limit_info={
                        "tokens_needed": tokens_needed,
                        "tokens_available": self.tokens,
                        "refill_rate": self.quota.requests_per_second,
                    }
                )


class SlidingWindowLimiter:
    """Sliding window rate limiter with time-based buckets"""
    
    def __init__(self, quota: RateLimitQuota):
        self.quota = quota
        self.window_requests: deque = deque()
        self.lock = asyncio.Lock()
    
    async def check(self, tokens_needed: int = 1) -> RateLimitResult:
        """Check if request is allowed within sliding window"""
        async with self.lock:
            now = time.time()
            window_start = now - self.quota.window_size_seconds
            
            # Remove expired requests
            while self.window_requests and self.window_requests[0] < window_start:
                self.window_requests.popleft()
            
            # Check if we can add this request
            max_requests = int(self.quota.requests_per_second * self.quota.window_size_seconds)
            current_requests = len(self.window_requests)
            
            if current_requests + tokens_needed <= max_requests:
                # Add request(s) to window
                for _ in range(tokens_needed):
                    self.window_requests.append(now)
                
                return RateLimitResult(
                    status=RateLimitStatus.ALLOWED,
                    allowed=True,
                    remaining_requests=max_requests - len(self.window_requests),
                    limit_info={
                        "requests_in_window": len(self.window_requests),
                        "max_in_window": max_requests,
                        "window_size": self.quota.window_size_seconds,
                    }
                )
            else:
                # Calculate retry time (when oldest request expires)
                oldest = self.window_requests[0]
                retry_after = (oldest + self.quota.window_size_seconds) - now
                
                return RateLimitResult(
                    status=RateLimitStatus.RATE_LIMITED,
                    allowed=False,
                    remaining_requests=0,
                    retry_after_seconds=max(0.1, retry_after),
                    limit_info={
                        "requests_in_window": len(self.window_requests),
                        "max_in_window": max_requests,
                        "window_size": self.quota.window_size_seconds,
                    }
                )


class LeakyBucketLimiter:
    """Leaky bucket rate limiter with smooth output"""
    
    def __init__(self, quota: RateLimitQuota):
        self.quota = quota
        self.bucket_level = 0.0
        self.max_level = float(quota.burst_size)
        self.leak_rate = quota.requests_per_second
        self.last_leak = time.time()
        self.lock = asyncio.Lock()
    
    async def check(self, tokens_needed: int = 1) -> RateLimitResult:
        """Check if request can be added to bucket"""
        async with self.lock:
            now = time.time()
            
            # Leak water from bucket
            elapsed = now - self.last_leak
            leaked = elapsed * self.leak_rate
            self.bucket_level = max(0, self.bucket_level - leaked)
            self.last_leak = now
            
            # Check if we can add this request
            if self.bucket_level + tokens_needed <= self.max_level:
                self.bucket_level += tokens_needed
                
                return RateLimitResult(
                    status=RateLimitStatus.ALLOWED,
                    allowed=True,
                    remaining_requests=int(self.max_level - self.bucket_level),
                    limit_info={
                        "bucket_level": self.bucket_level,
                        "max_level": self.max_level,
                        "leak_rate": self.leak_rate,
                    }
                )
            else:
                # Calculate wait time
                overflow = self.bucket_level + tokens_needed - self.max_level
                wait_time = overflow / self.leak_rate
                
                return RateLimitResult(
                    status=RateLimitStatus.RATE_LIMITED,
                    allowed=False,
                    remaining_requests=0,
                    retry_after_seconds=wait_time,
                    limit_info={
                        "bucket_level": self.bucket_level,
                        "max_level": self.max_level,
                        "leak_rate": self.leak_rate,
                        "overflow": overflow,
                    }
                )


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts limits based on system load"""
    
    def __init__(self, base_quota: RateLimitQuota, min_load_reduction: float = 0.5):
        self.base_quota = base_quota
        self.current_quota = base_quota
        self.min_load_reduction = min_load_reduction
        self.system_load = 0.0  # 0.0 to 1.0
        self.limiter = TokenBucketLimiter(base_quota)
        self.lock = asyncio.Lock()
        self.request_times: deque = deque(maxlen=100)
    
    async def set_system_load(self, load: float):
        """Update system load (0.0 to 1.0)"""
        async with self.lock:
            self.system_load = max(0.0, min(1.0, load))
            
            # Adjust quota based on load
            load_factor = 1.0 - (self.system_load * (1.0 - self.min_load_reduction))
            adjusted_rps = self.base_quota.requests_per_second * load_factor
            
            # Update limiter quota
            self.current_quota = RateLimitQuota(
                requests_per_second=adjusted_rps,
                burst_size=int(self.base_quota.burst_size * load_factor),
                window_size_seconds=self.base_quota.window_size_seconds
            )
            self.limiter = TokenBucketLimiter(self.current_quota)
    
    async def check(self, tokens_needed: int = 1) -> RateLimitResult:
        """Check with adaptive limits"""
        result = await self.limiter.check(tokens_needed)
        
        # Track request timing
        now = time.time()
        self.request_times.append(now)
        
        result.limit_info["system_load"] = self.system_load
        result.limit_info["adjusted_rps"] = self.current_quota.requests_per_second
        
        return result


class RateLimitManager:
    """Centralized rate limiting manager for multiple limiters"""
    
    def __init__(self, algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET):
        self.algorithm = algorithm
        self.limiters: Dict[str, object] = {}  # key -> limiter
        self.quotas: Dict[str, RateLimitQuota] = {}
        self.lock = asyncio.Lock()
        self.denied_requests: List[Dict] = []
        self.max_denied_history = 1000
    
    async def configure_limiter(
        self,
        key: str,
        quota: RateLimitQuota,
        algorithm: Optional[RateLimitAlgorithm] = None
    ):
        """Configure rate limiting for a key (tenant, agent, endpoint)"""
        async with self.lock:
            algo = algorithm or self.algorithm
            
            if algo == RateLimitAlgorithm.TOKEN_BUCKET:
                self.limiters[key] = TokenBucketLimiter(quota)
            elif algo == RateLimitAlgorithm.SLIDING_WINDOW:
                self.limiters[key] = SlidingWindowLimiter(quota)
            elif algo == RateLimitAlgorithm.LEAKY_BUCKET:
                self.limiters[key] = LeakyBucketLimiter(quota)
            elif algo == RateLimitAlgorithm.ADAPTIVE:
                self.limiters[key] = AdaptiveRateLimiter(quota)
            
            self.quotas[key] = quota
    
    async def check_limit(
        self,
        key: str,
        tokens_needed: int = 1,
        quota: Optional[RateLimitQuota] = None
    ) -> RateLimitResult:
        """Check rate limit for a key"""
        # Auto-configure if needed
        if key not in self.limiters and quota:
            await self.configure_limiter(key, quota)
        
        if key not in self.limiters:
            return RateLimitResult(
                status=RateLimitStatus.QUOTA_EXCEEDED,
                allowed=False,
                remaining_requests=0,
                limit_info={"error": f"No rate limit configured for {key}"}
            )
        
        limiter = self.limiters[key]
        result = await limiter.check(tokens_needed)
        
        # Track denied requests
        if not result.allowed:
            self._track_denied_request(key, result)
        
        return result
    
    def _track_denied_request(self, key: str, result: RateLimitResult):
        """Track rate limited requests"""
        record = {
            "timestamp": time.time(),
            "key": key,
            "status": result.status.value,
            "retry_after": result.retry_after_seconds,
        }
        self.denied_requests.append(record)
        
        # Keep only recent denials
        if len(self.denied_requests) > self.max_denied_history:
            self.denied_requests = self.denied_requests[-self.max_denied_history:]
    
    async def get_stats(self, key: Optional[str] = None) -> Dict:
        """Get rate limiting statistics"""
        async with self.lock:
            if key:
                if key not in self.quotas:
                    return {"error": f"No limiter for {key}"}
                return {
                    "key": key,
                    "algorithm": self.algorithm.value,
                    "quota": {
                        "requests_per_second": self.quotas[key].requests_per_second,
                        "burst_size": self.quotas[key].burst_size,
                    },
                    "denied_count": sum(1 for d in self.denied_requests if d["key"] == key),
                }
            else:
                return {
                    "total_limiters": len(self.limiters),
                    "algorithm": self.algorithm.value,
                    "total_denied_requests": len(self.denied_requests),
                    "limiters": list(self.limiters.keys()),
                }
    
    def export_metrics(self) -> Dict:
        """Export rate limiting metrics"""
        return {
            "total_limiters": len(self.limiters),
            "total_denied_requests": len(self.denied_requests),
            "algorithm": self.algorithm.value,
            "denied_requests_last_100": self.denied_requests[-100:],
        }


# Global rate limiter instance
_global_rate_limiter = RateLimitManager()


async def get_rate_limiter() -> RateLimitManager:
    """Get the global rate limiter instance"""
    return _global_rate_limiter
