"""
Session Manager for Theo - Conversational PII Tracker
Handles in-memory storage of conversation sessions and PII data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import uuid


@dataclass
class PIIEntity:
    """Represents a single PII entity detected in text."""
    text: str
    entity_type: str
    score: float
    start: int
    end: int
    color: str
    message_index: int


@dataclass
class Message:
    """Represents a single message in the conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    pii_entities: List[PIIEntity] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
            'pii_entities': [
                {
                    'text': e.text,
                    'entity_type': e.entity_type,
                    'score': e.score,
                    'start': e.start,
                    'end': e.end,
                    'color': e.color,
                    'message_index': e.message_index
                }
                for e in self.pii_entities
            ]
        }


@dataclass
class ConversationSession:
    """Represents a conversation session with accumulated PII."""
    session_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_inference: Optional[str] = None
    inference_cache_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'messages': [m.to_dict() for m in self.messages],
            'created_at': self.created_at,
            'last_inference': self.last_inference
        }


class SessionManager:
    """Manages in-memory conversation sessions."""

    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def get_or_create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """Get existing session or create a new one."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        new_id = session_id or str(uuid.uuid4())
        session = ConversationSession(session_id=new_id)
        self._sessions[new_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        pii_entities: List[PIIEntity]
    ) -> Message:
        """Add a message to a session."""
        session = self.get_or_create_session(session_id)

        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            pii_entities=pii_entities
        )
        session.messages.append(message)

        # Invalidate inference cache when new message is added
        session.inference_cache_hash = None

        return message

    def get_all_pii_entities(self, session_id: str) -> List[PIIEntity]:
        """Get all PII entities from all messages in a session."""
        session = self.get_session(session_id)
        if not session:
            return []

        all_entities = []
        for idx, message in enumerate(session.messages):
            for entity in message.pii_entities:
                # Create a copy with updated message_index
                entity_copy = PIIEntity(
                    text=entity.text,
                    entity_type=entity.entity_type,
                    score=entity.score,
                    start=entity.start,
                    end=entity.end,
                    color=entity.color,
                    message_index=idx
                )
                all_entities.append(entity_copy)

        return all_entities

    def update_inference(self, session_id: str, inference: str, cache_hash: str) -> None:
        """Update the inference for a session."""
        session = self.get_session(session_id)
        if session:
            session.last_inference = inference
            session.inference_cache_hash = cache_hash

    def reset_session(self, session_id: str) -> None:
        """Clear a session's data."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def get_message_count(self, session_id: str) -> int:
        """Get the number of messages in a session."""
        session = self.get_session(session_id)
        return len(session.messages) if session else 0
