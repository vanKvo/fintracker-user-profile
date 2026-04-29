"""
Outbound Ports — Abstract Base Classes defining what the domain needs from infrastructure.
The domain imports only these; it never touches boto3, DynamoDB, or HTTP libraries directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from domain.models import (
    SavingsGoal,
    UserProfile,
    UserSettings,
    WebSocketConnection,
)


class UserRepository(ABC):
    """Port: persistence operations for User identity and profile data."""

    @abstractmethod
    def resolve_user_id(self, cognito_sub: str) -> Optional[UUID]:
        """
        Resolves an external Cognito sub to the internal user_id UUID.

        Returns None if the sub has no mapping (e.g. first-time Google login
        before post-confirmation has run).
        """
        ...

    @abstractmethod
    def create_user(self, profile: UserProfile, settings: UserSettings) -> None:
        """
        Atomically creates the IDENTITY mapping, PROFILE, and default SETTINGS
        records via a single DynamoDB TransactWriteItems call.
        Idempotent — safe to call multiple times for the same sub.
        """
        ...

    @abstractmethod
    def get_profile(self, user_id: UUID) -> Optional[UserProfile]:
        ...

    @abstractmethod
    def get_settings(self, user_id: UUID) -> Optional[UserSettings]:
        ...

    @abstractmethod
    def update_settings(self, user_id: UUID, settings: UserSettings) -> None:
        ...

    @abstractmethod
    def delete_user(self, user_id: UUID) -> None:
        """Deletes all records (IDENTITY, PROFILE, SETTINGS, GOALs, WS) for user."""
        ...


class GoalRepository(ABC):
    """Port: persistence for Savings Goal CRUD."""

    @abstractmethod
    def list_goals(self, user_id: UUID) -> list[SavingsGoal]:
        ...

    @abstractmethod
    def save_goal(self, goal: SavingsGoal) -> SavingsGoal:
        ...

    @abstractmethod
    def delete_goal(self, user_id: UUID, goal_id: UUID) -> None:
        ...


class WebSocketRepository(ABC):
    """Port: persistence and retrieval of active WebSocket connections."""

    @abstractmethod
    def save_connection(self, connection: WebSocketConnection) -> None:
        ...

    @abstractmethod
    def get_connections(self, user_id: UUID) -> list[WebSocketConnection]:
        ...

    @abstractmethod
    def delete_connection(self, user_id: UUID, connection_id: str) -> None:
        ...


class EventPublisher(ABC):
    """Outbound Port: publish integration events to the event bus (EventBridge)."""

    @abstractmethod
    def publish_user_deleted(self, user_id: UUID) -> None:
        """
        Emits AccountDeleted event consumed by ledger-service to asynchronously
        purge the user's financial data.
        """
        ...
