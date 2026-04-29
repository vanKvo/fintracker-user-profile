"""
Unit Tests: UserProfileService domain logic.
Tests the domain in 100% isolation — all ports are mocked.
No AWS SDK, no DynamoDB, no real I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from domain.models import SubscriptionTier, UserProfile, UserSettings
from domain.services import UserNotFoundError, UserProfileService


@pytest.fixture
def user_repo():
    return MagicMock()


@pytest.fixture
def goal_repo():
    return MagicMock()


@pytest.fixture
def publisher():
    return MagicMock()


@pytest.fixture
def svc(user_repo, goal_repo, publisher):
    return UserProfileService(user_repo, goal_repo, publisher)


class TestRegisterUser:
    def test_creates_new_user_when_sub_not_mapped(self, svc, user_repo):
        user_repo.resolve_user_id.return_value = None
        user_repo.create_user.return_value = None

        profile = svc.register_user(
            cognito_sub="sub-123",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )

        assert profile.email == "alice@example.com"
        assert profile.subscription_tier == SubscriptionTier.FREE
        user_repo.create_user.assert_called_once()

    def test_returns_existing_profile_when_sub_already_mapped(self, svc, user_repo):
        existing_id = uuid4()
        existing_profile = UserProfile(
            user_id=existing_id, cognito_sub="sub-123", email="alice@example.com",
            first_name="Alice", last_name="Smith", phone_number=None,
            subscription_tier=SubscriptionTier.FREE, created_at=datetime.now(tz=timezone.utc)
        )
        user_repo.resolve_user_id.return_value = existing_id
        user_repo.get_profile.return_value = existing_profile

        profile = svc.register_user(
            cognito_sub="sub-123", email="alice@example.com",
            first_name="Alice", last_name="Smith"
        )

        assert profile.user_id == existing_id
        user_repo.create_user.assert_not_called()


class TestDeleteAccount:
    def test_deletes_user_and_publishes_event(self, svc, user_repo, publisher):
        user_id = uuid4()
        user_repo.resolve_user_id.return_value = user_id

        svc.delete_account(cognito_sub="sub-del")

        user_repo.delete_user.assert_called_once_with(user_id)
        publisher.publish_user_deleted.assert_called_once_with(user_id)

    def test_raises_when_user_not_found(self, svc, user_repo):
        user_repo.resolve_user_id.return_value = None
        with pytest.raises(UserNotFoundError):
            svc.delete_account(cognito_sub="unknown-sub")
