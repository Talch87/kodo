"""
Deadlock Detection and Prevention

Detects potential deadlocks in agent orchestration and provides
mechanisms for prevention and recovery.
"""

import time
from typing import Set, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import threading


class ResourceType(Enum):
    """Types of resources that can cause deadlocks."""
    LOCK = "lock"
    MESSAGE_QUEUE = "message_queue"
    SEMAPHORE = "semaphore"
    MEMORY = "memory"
    AGENT_SLOT = "agent_slot"


@dataclass
class ResourceRequest:
    """Represents a resource request."""
    agent_id: str
    resource_id: str
    resource_type: ResourceType
    timestamp: float = field(default_factory=time.time)
    timeout: float = 30.0  # seconds


@dataclass
class WaitForGraph:
    """Represents wait-for relationships between agents."""
    waiting: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    holding: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    
    def add_wait(self, waiter: str, holder: str):
        """Add wait relationship."""
        self.waiting[waiter].add(holder)
    
    def add_hold(self, agent: str, resource: str):
        """Add resource hold."""
        self.holding[agent].add(resource)
    
    def remove_wait(self, waiter: str, holder: str):
        """Remove wait relationship."""
        self.waiting[waiter].discard(holder)
    
    def remove_hold(self, agent: str, resource: str):
        """Remove resource hold."""
        self.holding[agent].discard(resource)
    
    def clear_agent(self, agent: str):
        """Clear all relationships for an agent."""
        self.waiting.pop(agent, None)
        self.holding.pop(agent, None)
        for waiters in self.waiting.values():
            waiters.discard(agent)


class DeadlockDetector:
    """Detects deadlock conditions using cycle detection."""
    
    def __init__(self):
        self.graph = WaitForGraph()
        self.detected_cycles: List[List[str]] = []
        self.last_check_time = time.time()
        self._lock = threading.Lock()
    
    def add_wait_edge(self, waiter: str, holder: str):
        """Add edge indicating agent is waiting."""
        with self._lock:
            self.graph.add_wait(waiter, holder)
    
    def remove_wait_edge(self, waiter: str, holder: str):
        """Remove edge indicating wait resolved."""
        with self._lock:
            self.graph.remove_wait(waiter, holder)
    
    def add_hold_resource(self, agent: str, resource: str):
        """Record that agent holds resource."""
        with self._lock:
            self.graph.add_hold(agent, resource)
    
    def release_resource(self, agent: str, resource: str):
        """Record that agent released resource."""
        with self._lock:
            self.graph.remove_hold(agent, resource)
    
    def detect_deadlock(self) -> List[List[str]]:
        """
        Detect cycles in wait-for graph using cycle detection.
        
        Returns:
            List of cycles (each cycle is a list of agent IDs)
        """
        cycles = []
        visited = set()
        rec_stack = set()
        parent_map = {}
        
        def dfs_visit(node: str, depth: int = 0) -> Optional[str]:
            """DFS to find cycles. Returns node that completes a cycle, or None."""
            if depth > len(self.graph.waiting) + 10:  # Prevent infinite recursion
                return None
            
            if node in rec_stack:
                return node  # Found cycle back to this node
            
            if node in visited:
                return None
            
            visited.add(node)
            rec_stack.add(node)
            
            # Check if node has waiters
            if node not in self.graph.waiting:
                rec_stack.discard(node)
                return None
            
            # Check each waiter
            for neighbor in self.graph.waiting[node]:
                parent_map[neighbor] = node
                cycle_node = dfs_visit(neighbor, depth + 1)
                if cycle_node is not None:
                    # Reconstruct cycle
                    cycle = [neighbor]
                    current = node
                    while current != neighbor and current is not None:
                        cycle.append(current)
                        current = parent_map.get(current)
                    if current == neighbor:
                        cycles.append(cycle)
                    rec_stack.discard(node)
                    return None
            
            rec_stack.discard(node)
            return None
        
        # Check all nodes
        try:
            for agent in list(self.graph.waiting.keys()):
                if agent not in visited:
                    parent_map.clear()
                    dfs_visit(agent)
        except RecursionError:
            # If we hit recursion limit, mark as potential deadlock
            cycles.append(list(self.graph.waiting.keys()))
        
        self.detected_cycles = cycles
        self.last_check_time = time.time()
        return cycles
    
    def has_deadlock(self) -> bool:
        """Check if any deadlock exists."""
        cycles = self.detect_deadlock()
        return len(cycles) > 0
    
    def get_agents_in_deadlock(self) -> Set[str]:
        """Get set of agents involved in deadlock."""
        agents = set()
        for cycle in self.detected_cycles:
            agents.update(cycle)
        return agents
    
    def clear_agent(self, agent: str):
        """Clear all wait/hold relationships for an agent."""
        with self._lock:
            self.graph.clear_agent(agent)
    
    def get_metrics(self) -> dict:
        """Get deadlock detection metrics."""
        with self._lock:
            return {
                'deadlock_detected': self.has_deadlock(),
                'cycle_count': len(self.detected_cycles),
                'agents_in_deadlock': len(self.get_agents_in_deadlock()),
                'wait_edges': sum(len(v) for v in self.graph.waiting.values()),
                'last_check_time': self.last_check_time,
            }


class DeadlockPrevention:
    """Prevents deadlocks through ordering and timeouts."""
    
    def __init__(self):
        self.detector = DeadlockDetector()
        self.timeouts: Dict[str, float] = {}  # agent_id -> timeout_at
        self.resource_order: List[str] = []  # Global resource ordering
    
    def set_global_resource_order(self, resources: List[str]):
        """Set global ordering of resources to prevent circular waits."""
        self.resource_order = resources
    
    def get_resource_priority(self, resource: str) -> int:
        """Get priority of resource (lower = higher priority)."""
        if resource in self.resource_order:
            return self.resource_order.index(resource)
        return len(self.resource_order)
    
    def check_circular_wait_violation(
        self,
        agent: str,
        current_resource: str,
        requested_resource: str
    ) -> bool:
        """
        Check if acquiring requested resource would violate circular wait.
        
        With global resource ordering, an agent can only request resources
        in order of priority. Returns True if requesting a lower-priority
        resource after holding higher-priority one.
        """
        current_priority = self.get_resource_priority(current_resource)
        requested_priority = self.get_resource_priority(requested_resource)
        return requested_priority < current_priority
    
    def set_request_timeout(self, agent: str, timeout_seconds: float):
        """Set timeout for agent requests (break hold_and_wait)."""
        self.timeouts[agent] = time.time() + timeout_seconds
    
    def has_request_timeout(self, agent: str) -> bool:
        """Check if agent's request has timed out."""
        if agent not in self.timeouts:
            return False
        return time.time() > self.timeouts[agent]
    
    def handle_timeout(self, agent: str):
        """Handle timeout by forcing resource release."""
        self.detector.clear_agent(agent)
        self.timeouts.pop(agent, None)
    
    def detect_and_break_deadlock(self, victim_selection="lru") -> Optional[str]:
        """
        Detect deadlock and break it by terminating a victim agent.
        
        Args:
            victim_selection: Strategy for selecting victim ("lru", "min_resources", "min_priority")
        
        Returns:
            ID of terminated agent or None
        """
        if not self.detector.has_deadlock():
            return None
        
        agents = self.detector.get_agents_in_deadlock()
        if not agents:
            return None
        
        # Select victim based on strategy
        victim = None
        if victim_selection == "lru":
            # Least recently used (simplest)
            victim = min(agents)
        elif victim_selection == "min_resources":
            # Agent holding fewest resources
            victim = min(
                agents,
                key=lambda a: len(self.detector.graph.holding.get(a, set()))
            )
        elif victim_selection == "min_priority":
            # Agent with lowest priority (highest numeric ID)
            victim = max(agents)
        
        # Clear the victim's resources
        if victim:
            self.detector.clear_agent(victim)
            self.timeouts.pop(victim, None)
        
        return victim


class DeadlockAvoidanceMonitor:
    """Monitors for potential deadlock conditions and alerts."""
    
    def __init__(self, detection_interval: float = 5.0):
        self.detector = DeadlockDetector()
        self.detection_interval = detection_interval
        self.last_detection = 0.0
        self.deadlock_events: List[dict] = []
    
    def check_for_deadlock(self) -> bool:
        """Check for deadlock, respecting interval."""
        now = time.time()
        if now - self.last_detection < self.detection_interval:
            return self.detector.has_deadlock()
        
        self.last_detection = now
        has_deadlock = self.detector.has_deadlock()
        
        if has_deadlock:
            event = {
                'timestamp': now,
                'detected': True,
                'cycles': self.detector.detected_cycles,
                'affected_agents': list(self.detector.get_agents_in_deadlock()),
            }
            self.deadlock_events.append(event)
        
        return has_deadlock
    
    def get_deadlock_history(self, max_events: int = 100) -> List[dict]:
        """Get recent deadlock events."""
        return self.deadlock_events[-max_events:]
    
    def get_metrics(self) -> dict:
        """Get monitoring metrics."""
        return {
            'detector_metrics': self.detector.get_metrics(),
            'total_deadlock_events': len(self.deadlock_events),
            'last_deadlock_time': (
                self.deadlock_events[-1]['timestamp']
                if self.deadlock_events
                else None
            ),
        }
