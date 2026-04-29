"""
DI Container — wires infrastructure adapters to domain ports.
This is the only file with knowledge of both layers.
"""
from __future__ import annotations

import os

from domain.ports import EventPublisher, GoalRepository, UserRepository
from domain.services import UserProfileService
from infrastructure.dynamodb_repository import (
    DynamoDBGoalRepository,
    DynamoDBUserRepository,
    DynamoDBWebSocketRepository,
)
from infrastructure.eventbridge_publisher import EventBridgePublisher

_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
_EVENT_BUS  = os.environ["EVENT_BUS_NAME"]

# Instantiated once at Lambda cold-start and reused across invocations
_user_repo:   UserRepository   = DynamoDBUserRepository(_TABLE_NAME)
_goal_repo:   GoalRepository   = DynamoDBGoalRepository(_TABLE_NAME)
_ws_repo  :   DynamoDBWebSocketRepository = DynamoDBWebSocketRepository(_TABLE_NAME)
_publisher:   EventPublisher   = EventBridgePublisher(_EVENT_BUS)

service = UserProfileService(
    user_repo=_user_repo,
    goal_repo=_goal_repo,
    event_publisher=_publisher,
)
