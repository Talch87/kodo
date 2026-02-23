"""Inter-Agent Communication - Enable agents to collaborate and ask questions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class MessageType(Enum):
    """Types of messages agents can send."""
    QUESTION = "question"              # Asking for advice
    FEEDBACK = "feedback"              # Providing feedback
    CLARIFICATION = "clarification"    # Asking for clarification
    CONCERN = "concern"                # Raising a concern
    SUGGESTION = "suggestion"          # Suggesting an approach
    STATUS_UPDATE = "status_update"    # Reporting progress
    REQUEST_HELP = "request_help"      # Asking for help


@dataclass
class AgentMessage:
    """Message from one agent to another."""
    sender: str
    recipient: str
    message_type: MessageType
    content: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    response: Optional[str] = None
    response_timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class AgentCommunicationHub:
    """Central hub for inter-agent communication."""
    
    def __init__(self, message_log: Path = Path(".kodo/agent_messages.jsonl")):
        self.message_log = message_log
        self.message_log.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory message queues
        self.pending_messages: Dict[str, List[AgentMessage]] = {}
        self.message_history: List[AgentMessage] = []
    
    def send_message(
        self,
        sender: str,
        recipient: str,
        message_type: MessageType,
        content: str,
        context: Optional[Dict] = None,
    ) -> AgentMessage:
        """Send a message from one agent to another."""
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            content=content,
            context=context or {},
        )
        
        # Queue message for recipient
        if recipient not in self.pending_messages:
            self.pending_messages[recipient] = []
        self.pending_messages[recipient].append(message)
        
        # Log message
        self._log_message(message)
        self.message_history.append(message)
        
        return message
    
    def get_pending_messages(self, agent: str) -> List[AgentMessage]:
        """Get all pending messages for an agent."""
        return self.pending_messages.pop(agent, [])
    
    def respond_to_message(self, message_id: int, response: str) -> None:
        """Record a response to a message."""
        if 0 <= message_id < len(self.message_history):
            msg = self.message_history[message_id]
            msg.response = response
            msg.response_timestamp = datetime.now().isoformat()
            self._log_message(msg)
    
    def get_agent_conversations(self, agent: str) -> List[tuple]:
        """Get all conversations involving an agent."""
        conversations = []
        for msg in self.message_history:
            if msg.sender == agent or msg.recipient == agent:
                conversations.append((msg.sender, msg.recipient, msg.message_type.value, msg.content, msg.response))
        return conversations
    
    def format_messages_for_agent(self, agent: str) -> str:
        """Format pending messages as a prompt for an agent."""
        messages = self.get_pending_messages(agent)
        
        if not messages:
            return ""
        
        lines = [
            f"# Messages for {agent}",
            "",
            f"You have {len(messages)} incoming message(s):",
            ""
        ]
        
        for i, msg in enumerate(messages, 1):
            lines.append(f"## Message {i} from {msg.sender}")
            lines.append(f"Type: {msg.message_type.value.upper()}")
            lines.append(f"Time: {msg.timestamp}")
            lines.append("")
            lines.append(msg.content)
            
            if msg.context:
                lines.append("")
                lines.append("Context:")
                for key, val in msg.context.items():
                    lines.append(f"- {key}: {val}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_collaboration_suggestions(self) -> List[str]:
        """Analyze message patterns and suggest collaborations."""
        suggestions = []
        
        # Count who talks to whom
        conversations = {}
        for msg in self.message_history:
            key = (msg.sender, msg.recipient)
            conversations[key] = conversations.get(key, 0) + 1
        
        # Find bottlenecks (agents who need help)
        receivers = {}
        for (_, recipient), count in conversations.items():
            receivers[recipient] = receivers.get(recipient, 0) + count
        
        # Suggest multi-agent reviews for heavily-questioned work
        for agent, count in sorted(receivers.items(), key=lambda x: x[1], reverse=True)[:3]:
            if count >= 3:
                suggestions.append(
                    f"Agent '{agent}' received {count} messages - consider doing pair programming"
                )
        
        return suggestions
    
    def _log_message(self, message: AgentMessage) -> None:
        """Log message to file."""
        with open(self.message_log, "a") as f:
            data = {
                "sender": message.sender,
                "recipient": message.recipient,
                "message_type": message.message_type.value,
                "content": message.content,
                "context": message.context,
                "timestamp": message.timestamp,
                "response": message.response,
                "response_timestamp": message.response_timestamp,
            }
            f.write(json.dumps(data) + "\n")


class AgentAsksFor:
    """Helper methods for agents to ask questions in standardized ways."""
    
    @staticmethod
    def ask_for_design_review(
        hub: AgentCommunicationHub,
        sender: str,
        recipient: str,
        design: str,
        concerns: List[str] = None,
    ) -> AgentMessage:
        """Ask another agent to review a design."""
        content = f"""Please review this design:

{design}

Specific concerns:
{chr(10).join(f"- {c}" for c in (concerns or ["No specific concerns"]))}
"""
        return hub.send_message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.QUESTION,
            content=content,
            context={"type": "design_review"}
        )
    
    @staticmethod
    def raise_concern(
        hub: AgentCommunicationHub,
        sender: str,
        recipient: str,
        concern: str,
        severity: str = "medium",
    ) -> AgentMessage:
        """Raise a concern about work."""
        return hub.send_message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.CONCERN,
            content=concern,
            context={"severity": severity}
        )
    
    @staticmethod
    def request_refactoring_advice(
        hub: AgentCommunicationHub,
        sender: str,
        recipient: str,
        code: str,
        issue: str,
    ) -> AgentMessage:
        """Ask for help refactoring code."""
        content = f"""I need help refactoring this code:

```
{code}
```

Issue: {issue}

What would be a better approach?
"""
        return hub.send_message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.REQUEST_HELP,
            content=content,
            context={"type": "refactoring"}
        )
    
    @staticmethod
    def suggest_optimization(
        hub: AgentCommunicationHub,
        sender: str,
        recipient: str,
        optimization: str,
        impact: str,
    ) -> AgentMessage:
        """Suggest an optimization to another agent's work."""
        content = f"""I have a suggestion for optimization:

{optimization}

Potential impact: {impact}

Would you like me to implement this?
"""
        return hub.send_message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.SUGGESTION,
            content=content,
            context={"type": "optimization"}
        )
