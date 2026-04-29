"""
DynamoDB Adapter — implements UserRepository, GoalRepository, and WebSocketRepository.

Single-Table Design on FinTracker_UserProfile:
  IDENTITY#<cognito_sub>  MAPPING            → internal_user_id
  USER#<user_id>          PROFILE            → email, name, tier, created_at
  USER#<user_id>          SETTINGS           → currency, timezone, notification_prefs
  USER#<user_id>          GOAL#<goal_id>     → goal details
  USER#<user_id>          WS#<connection_id> → websocket endpoint, ttl
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.schemas.models import (
    NotificationChannel,
    NotificationPreferences,
    SavingsGoal,
    SubscriptionTier,
    UserProfile,
    UserSettings,
    WebSocketConnection,
)


log = logging.getLogger(__name__)

_TABLE_ENV = "DYNAMODB_TABLE_NAME"


class DynamoDBUserRepository:
    """Outbound Adapter: DynamoDB implementation of UserRepository."""

    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    # ── Identity Mapping ────────────────────────────────────────────────────

    def resolve_user_id(self, cognito_sub: str) -> Optional[UUID]:
        try:
            resp = self._table.get_item(
                Key={"PK": f"IDENTITY#{cognito_sub}", "SK": "MAPPING"},
                ProjectionExpression="internal_user_id",
            )
            item = resp.get("Item")
            return UUID(item["internal_user_id"]) if item else None
        except ClientError as exc:
            log.error("DynamoDB error resolving sub. sub=%s error=%s", cognito_sub, exc)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def create_user(self, profile: UserProfile, settings: UserSettings) -> None:
        """
        Atomically writes:
          - IDENTITY mapping (cognito_sub → internal user_id)
          - PROFILE record
          - SETTINGS record
        ON CONDITION that the identity does not already exist (idempotency guard).
        """
        user_id_str = str(profile.user_id)
        try:
            self._table.meta.client.transact_write(Items=[
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {
                            "PK": f"IDENTITY#{profile.cognito_sub}",
                            "SK": "MAPPING",
                            "internal_user_id": user_id_str,
                        },
                        # Idempotency: only write if no mapping exists yet
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {
                            "PK": f"USER#{user_id_str}",
                            "SK": "PROFILE",
                            "email": profile.email,
                            "first_name": profile.first_name,
                            "last_name": profile.last_name,
                            "phone_number": profile.phone_number,
                            "subscription_tier": profile.subscription_tier.value,
                            "created_at": profile.created_at.isoformat(),
                        },
                    }
                },
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {
                            "PK": f"USER#{user_id_str}",
                            "SK": "SETTINGS",
                            "currency": settings.currency,
                            "timezone": settings.timezone,
                            "notification_prefs": json.dumps(
                                {
                                    "channel": settings.notification_prefs.channel.value,
                                    "budget_alerts": settings.notification_prefs.budget_alerts,
                                    "statement_processed": settings.notification_prefs.statement_processed,
                                }
                            ),
                        },
                    }
                },
            ])
        except ClientError as exc:
            # ConditionalCheckFailedException means already registered — safe
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                log.info("User already exists in DynamoDB, skipping. sub=%s", profile.cognito_sub)
                return
            raise

    def get_profile(self, user_id: UUID) -> Optional[UserProfile]:
        resp = self._table.get_item(
            Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        )
        item = resp.get("Item")
        if not item:
            return None
        return UserProfile(
            user_id=user_id,
            cognito_sub="",  # Not stored in PROFILE row for security
            email=item["email"],
            first_name=item["first_name"],
            last_name=item["last_name"],
            phone_number=item.get("phone_number"),
            subscription_tier=SubscriptionTier(item["subscription_tier"]),
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def get_settings(self, user_id: UUID) -> Optional[UserSettings]:
        resp = self._table.get_item(
            Key={"PK": f"USER#{user_id}", "SK": "SETTINGS"},
        )
        item = resp.get("Item")
        if not item:
            return None
        prefs_raw = json.loads(item.get("notification_prefs", "{}"))
        return UserSettings(
            user_id=user_id,
            currency=item.get("currency", "USD"),
            timezone=item.get("timezone", "UTC"),
            notification_prefs=NotificationPreferences(
                channel=NotificationChannel(prefs_raw.get("channel", "EMAIL")),
                budget_alerts=prefs_raw.get("budget_alerts", True),
                statement_processed=prefs_raw.get("statement_processed", True),
            ),
        )

    def update_settings(self, user_id: UUID, settings: UserSettings) -> None:
        self._table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": "SETTINGS"},
            UpdateExpression="SET #cur = :c, #tz = :t, notification_prefs = :n",
            ExpressionAttributeNames={"#cur": "currency", "#tz": "timezone"},
            ExpressionAttributeValues={
                ":c": settings.currency,
                ":t": settings.timezone,
                ":n": json.dumps({
                    "channel": settings.notification_prefs.channel.value,
                    "budget_alerts": settings.notification_prefs.budget_alerts,
                    "statement_processed": settings.notification_prefs.statement_processed,
                }),
            },
        )

    def delete_user(self, user_id: UUID) -> None:
        """Deletes all items with PK=USER#<user_id> using a paginated Query + BatchWrite."""
        pk = f"USER#{user_id}"
        resp = self._table.query(KeyConditionExpression=Key("PK").eq(pk))
        items = resp.get("Items", [])
        with self._table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        log.info("Deleted %d DynamoDB records for user_id=%s", len(items), user_id)


class DynamoDBGoalRepository:
    """Outbound Adapter: DynamoDB implementation of GoalRepository."""

    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    def list_goals(self, user_id: UUID) -> list[SavingsGoal]:
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("GOAL#"),
        )
        return [self._map(item, user_id) for item in resp.get("Items", [])]

    def save_goal(self, goal: SavingsGoal) -> SavingsGoal:
        self._table.put_item(Item={
            "PK": f"USER#{goal.user_id}",
            "SK": f"GOAL#{goal.goal_id}",
            "goal_name": goal.goal_name,
            "target_amount": str(goal.target_amount),
            "current_amount": str(goal.current_amount),
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
        })
        return goal

    def delete_goal(self, user_id: UUID, goal_id: UUID) -> None:
        self._table.delete_item(
            Key={"PK": f"USER#{user_id}", "SK": f"GOAL#{goal_id}"},
        )

    @staticmethod
    def _map(item: dict, user_id: UUID) -> SavingsGoal:
        goal_id = UUID(item["SK"].removeprefix("GOAL#"))
        return SavingsGoal(
            goal_id=goal_id,
            user_id=user_id,
            goal_name=item["goal_name"],
            target_amount=float(item["target_amount"]),
            current_amount=float(item["current_amount"]),
            deadline=datetime.fromisoformat(item["deadline"]) if item.get("deadline") else None,
        )


class DynamoDBWebSocketRepository:
    """Outbound Adapter: DynamoDB implementation of WebSocketRepository."""

    def __init__(self, table_name: str) -> None:
        self._table = boto3.resource("dynamodb").Table(table_name)

    def save_connection(self, connection: WebSocketConnection) -> None:
        self._table.put_item(Item={
            "PK": f"USER#{connection.user_id}",
            "SK": f"WS#{connection.connection_id}",
            "endpoint_url": connection.endpoint_url,
            "connected_at": connection.connected_at.isoformat(),
            "ttl": connection.ttl,
        })

    def get_connections(self, user_id: UUID) -> list[WebSocketConnection]:
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("WS#"),
        )
        return [self._map(item, user_id) for item in resp.get("Items", [])]

    def delete_connection(self, user_id: UUID, connection_id: str) -> None:
        self._table.delete_item(
            Key={"PK": f"USER#{user_id}", "SK": f"WS#{connection_id}"},
        )

    @staticmethod
    def _map(item: dict, user_id: UUID) -> WebSocketConnection:
        return WebSocketConnection(
            user_id=user_id,
            connection_id=item["SK"].removeprefix("WS#"),
            endpoint_url=item["endpoint_url"],
            connected_at=datetime.fromisoformat(item["connected_at"]),
            ttl=int(item["ttl"]),
        )
