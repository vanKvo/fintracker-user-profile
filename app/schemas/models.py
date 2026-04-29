"""
Domain Models — pure Python dataclasses with no external dependencies.
Represents the core business entities for the user-profile-service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class SubscriptionTier(str, Enum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"


class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    NONE = "NONE"


@dataclass(frozen=True)
class NotificationPreferences:
    channel: NotificationChannel = NotificationChannel.EMAIL
    budget_alerts: bool = True
    statement_processed: bool = True


@dataclass(frozen=True)
class UserProfile:
    """
    Core user identity record.

    user_id is our internal UUID — fully decoupled from the external
    identity provider (Cognito sub). This ensures IdP portability.
    """
    user_id: UUID
    cognito_sub: str
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str]
    subscription_tier: SubscriptionTier
    created_at: datetime


@dataclass(frozen=True)
class UserSettings:
    """
    User preferences, separated from profile to keep profile reads lightweight.
    MFA state is intentionally excluded — natively owned by Cognito.
    """
    user_id: UUID
    currency: str        # ISO 4217, e.g. "USD"
    timezone: str        # IANA tz, e.g. "America/New_York"
    notification_prefs: NotificationPreferences = field(
        default_factory=NotificationPreferences
    )


@dataclass(frozen=True)
class SavingsGoal:
    """
    User-defined financial goal used for the 'Safe to Spend' dashboard metric.
    """
    goal_id: UUID
    user_id: UUID
    goal_name: str
    target_amount: float
    current_amount: float
    deadline: Optional[datetime]


@dataclass(frozen=True)
class WebSocketConnection:
    """
    Ephemeral record of an active API Gateway WebSocket connection.
    Used to push real-time domain events (e.g. statement processed) to the UI.
    """
    user_id: UUID
    connection_id: str
    endpoint_url: str
    connected_at: datetime
    ttl: int  # Unix epoch for DynamoDB TTL auto-expiry
