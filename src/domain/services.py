"""
Domain Service — pure business logic, zero infrastructure dependencies.
All dependencies are injected as Port abstractions via constructor injection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from domain.models import (
    NotificationPreferences,
    SavingsGoal,
    SubscriptionTier,
    UserProfile,
    UserSettings,
)
from domain.ports import EventPublisher, GoalRepository, UserRepository

log = logging.getLogger(__name__)


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class UserProfileService:
    """
    Orchestrates all user lifecycle workflows.

    Implements the business rules for registration, profile fetching,
    account deletion, and savings goal management.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        goal_repo: GoalRepository,
        event_publisher: EventPublisher,
    ) -> None:
        self._user_repo = user_repo
        self._goal_repo = goal_repo
        self._event_publisher = event_publisher

    # ── Workflow 1.1: Registration / Post-Confirmation ──────────────────────

    def register_user(
        self,
        *,
        cognito_sub: str,
        email: str,
        first_name: str,
        last_name: str,
    ) -> UserProfile:
        """
        Called by the Cognito Post-Confirmation Lambda trigger.

        Generates a stable internal UUID and atomically persists:
        - The IDENTITY# mapping (cognito_sub → user_id)
        - The PROFILE# record
        - Default SETTINGS# record

        Idempotent: if the sub already exists the existing profile is returned.
        """
        existing_id = self._user_repo.resolve_user_id(cognito_sub)
        if existing_id is not None:
            log.info("User already registered. cognito_sub=%s user_id=%s", cognito_sub, existing_id)
            profile = self._user_repo.get_profile(existing_id)
            if profile:
                return profile

        user_id = uuid4()
        profile = UserProfile(
            user_id=user_id,
            cognito_sub=cognito_sub,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=None,
            subscription_tier=SubscriptionTier.FREE,
            created_at=datetime.now(tz=timezone.utc),
        )
        default_settings = UserSettings(
            user_id=user_id,
            currency="USD",
            timezone="America/New_York",
            notification_prefs=NotificationPreferences(),
        )

        self._user_repo.create_user(profile, default_settings)
        log.info("Registered new user. user_id=%s email=%s", user_id, email)
        return profile

    # ── Workflow 1.3: Fetch Profile & Settings ──────────────────────────────

    def get_profile_and_settings(
        self, *, cognito_sub: str
    ) -> tuple[UserProfile, UserSettings]:
        """
        Resolves the cognito_sub to our internal user_id then fetches
        profile and settings in a single logical operation.

        Raises UserNotFoundError if the sub has no registered mapping.
        """
        user_id = self._resolve_or_raise(cognito_sub)
        profile = self._user_repo.get_profile(user_id)
        settings = self._user_repo.get_settings(user_id)

        if profile is None or settings is None:
            raise UserNotFoundError(f"Profile data missing for user_id={user_id}")

        return profile, settings

    # ── Workflow 1.4: Account Offboarding ──────────────────────────────────

    def delete_account(self, *, cognito_sub: str) -> None:
        """
        Full account offboarding workflow:
        1. Resolves the internal user_id.
        2. Deletes all DynamoDB records (profile, settings, goals, sockets).
        3. Publishes AccountDeleted event — ledger-service listens to purge
           financial records asynchronously (decoupled via EventBridge).
        """
        user_id = self._resolve_or_raise(cognito_sub)
        self._user_repo.delete_user(user_id)
        self._event_publisher.publish_user_deleted(user_id)
        log.info("Account offboarded. user_id=%s", user_id)

    # ── Workflow 1.5: Savings Goals ─────────────────────────────────────────

    def list_goals(self, *, cognito_sub: str) -> list[SavingsGoal]:
        user_id = self._resolve_or_raise(cognito_sub)
        return self._goal_repo.list_goals(user_id)

    def create_goal(
        self,
        *,
        cognito_sub: str,
        goal_name: str,
        target_amount: float,
        current_amount: float = 0.0,
        deadline: Optional[datetime] = None,
    ) -> SavingsGoal:
        user_id = self._resolve_or_raise(cognito_sub)
        goal = SavingsGoal(
            goal_id=uuid4(),
            user_id=user_id,
            goal_name=goal_name,
            target_amount=target_amount,
            current_amount=current_amount,
            deadline=deadline,
        )
        return self._goal_repo.save_goal(goal)

    def delete_goal(self, *, cognito_sub: str, goal_id: UUID) -> None:
        user_id = self._resolve_or_raise(cognito_sub)
        self._goal_repo.delete_goal(user_id, goal_id)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _resolve_or_raise(self, cognito_sub: str) -> UUID:
        user_id = self._user_repo.resolve_user_id(cognito_sub)
        if user_id is None:
            raise UserNotFoundError(f"No user mapping found for sub={cognito_sub}")
        return user_id
