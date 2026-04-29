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

from app.schemas.models import SubscriptionTier, UserProfile, UserSettings
from app.services.services import UserNotFoundError, UserProfileService


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


class TestGetProfileAndSettings:
    def test_returns_both_when_user_exists(self, svc, user_repo):
        user_id = uuid4()
        profile = UserProfile(
            user_id=user_id, cognito_sub="sub", email="a@b.com",
            first_name="A", last_name="B", phone_number=None,
            subscription_tier=SubscriptionTier.FREE, created_at=datetime.now(tz=timezone.utc)
        )
        settings = UserSettings(user_id=user_id, currency="USD", timezone="UTC")
        
        user_repo.resolve_user_id.return_value = user_id
        user_repo.get_profile.return_value = profile
        user_repo.get_settings.return_value = settings

        res_p, res_s = svc.get_profile_and_settings(cognito_sub="sub")
        
        assert res_p == profile
        assert res_s == settings

    def test_raises_when_profile_missing(self, svc, user_repo):
        user_id = uuid4()
        user_repo.resolve_user_id.return_value = user_id
        user_repo.get_profile.return_value = None
        
        with pytest.raises(UserNotFoundError, match="Profile data missing"):
            svc.get_profile_and_settings(cognito_sub="sub")


class TestSavingsGoals:
    def test_list_goals(self, svc, user_repo, goal_repo):
        user_id = uuid4()
        user_repo.resolve_user_id.return_value = user_id
        goal_repo.list_goals.return_value = ["goal1", "goal2"]

        goals = svc.list_goals(cognito_sub="sub")
        assert goals == ["goal1", "goal2"]
        goal_repo.list_goals.assert_called_once_with(user_id)

    def test_create_goal(self, svc, user_repo, goal_repo):
        user_id = uuid4()
        user_repo.resolve_user_id.return_value = user_id
        goal_repo.save_goal.side_effect = lambda x: x

        goal = svc.create_goal(
            cognito_sub="sub",
            goal_name="Save for car",
            target_amount=10000.0
        )

        assert goal.goal_name == "Save for car"
        assert goal.target_amount == 10000.0
        assert goal.user_id == user_id
        goal_repo.save_goal.assert_called_once()

    def test_delete_goal(self, svc, user_repo, goal_repo):
        user_id = uuid4()
        user_repo.resolve_user_id.return_value = user_id
        goal_id = uuid4()

        svc.delete_goal(cognito_sub="sub", goal_id=goal_id)
        
        goal_repo.delete_goal.assert_called_once_with(user_id, goal_id)
