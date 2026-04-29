"""
DI Container — wires infrastructure adapters to domain ports.
This is the only file with knowledge of both layers.
"""
from __future__ import annotations

import os

from app.services.services import UserProfileService
from app.crud.dynamodb_repository import (
    DynamoDBGoalRepository,
    DynamoDBUserRepository,
    DynamoDBWebSocketRepository,
)
from app.services.eventbridge_publisher import EventBridgePublisher

_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
_EVENT_BUS  = os.environ["EVENT_BUS_NAME"]

# Instantiated once at Lambda cold-start and reused across invocations
_user_repo   = DynamoDBUserRepository(_TABLE_NAME)
_goal_repo   = DynamoDBGoalRepository(_TABLE_NAME)
_ws_repo     = DynamoDBWebSocketRepository(_TABLE_NAME)
_publisher   = EventBridgePublisher(_EVENT_BUS)

service = UserProfileService(
    user_repo=_user_repo,
    goal_repo=_goal_repo,
    event_publisher=_publisher,
)
