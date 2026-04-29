"""
Inbound Adapter: WebSocket Lambda handlers for real-time push notifications (Workflow 1.6).

Three routes handled:
  $connect    — stores the connection tied to the user
  $disconnect — cleans up the connection record
  $default    — no-op placeholder (push is server-initiated, not client-initiated)
"""
from __future__ import annotations

import logging
import time

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from datetime import datetime, timezone
from uuid import UUID

import boto3

from config.container import _ws_repo
from domain.models import WebSocketConnection

logger = Logger(service="user-profile-service")

_WS_TTL_SECONDS = 2 * 60 * 60  # 2 hours


def _parse_user_id(event: dict) -> UUID:
    """Cognito authorizer injects user_id claim into WebSocket connect events."""
    return UUID(event["requestContext"]["authorizer"]["userId"])


@logger.inject_lambda_context(log_event=False)
def connect_handler(event: dict, context: LambdaContext) -> dict:
    connection_id = event["requestContext"]["connectionId"]
    domain        = event["requestContext"]["domainName"]
    stage         = event["requestContext"]["stage"]
    endpoint_url  = f"https://{domain}/{stage}"

    try:
        user_id = _parse_user_id(event)
        _ws_repo.save_connection(WebSocketConnection(
            user_id=user_id,
            connection_id=connection_id,
            endpoint_url=endpoint_url,
            connected_at=datetime.now(tz=timezone.utc),
            ttl=int(time.time()) + _WS_TTL_SECONDS,
        ))
        logger.info("WebSocket connected", extra={"connection_id": connection_id, "user_id": str(user_id)})
        return {"statusCode": 200}
    except Exception:
        logger.exception("Failed to store WebSocket connection")
        return {"statusCode": 500}


@logger.inject_lambda_context(log_event=False)
def disconnect_handler(event: dict, context: LambdaContext) -> dict:
    connection_id = event["requestContext"]["connectionId"]
    try:
        user_id = _parse_user_id(event)
        _ws_repo.delete_connection(user_id, connection_id)
        logger.info("WebSocket disconnected", extra={"connection_id": connection_id})
    except Exception:
        logger.exception("Failed to delete WebSocket connection")
    return {"statusCode": 200}


def push_to_user(user_id: UUID, payload: dict) -> None:
    """
    Utility called by other Lambda functions (e.g. data-pipeline completion event)
    to push a message to all active WebSocket connections of a user.
    """
    import json
    connections = _ws_repo.get_connections(user_id)
    for conn in connections:
        try:
            apigw = boto3.client("apigatewaymanagementapi", endpoint_url=conn.endpoint_url)
            apigw.post_to_connection(
                ConnectionId=conn.connection_id,
                Data=json.dumps(payload).encode(),
            )
        except apigw.exceptions.GoneException:
            # Stale connection — delete it
            _ws_repo.delete_connection(user_id, conn.connection_id)
            logger.info("Deleted stale WebSocket connection", extra={"connection_id": conn.connection_id})
        except Exception:
            logger.exception("Failed to push to connection", extra={"connection_id": conn.connection_id})
