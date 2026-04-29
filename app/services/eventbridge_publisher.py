"""
EventBridge Adapter — outbound port implementation for integration events.

Publishes domain events to EventBridge so downstream services (ledger-service)
can react asynchronously without direct coupling.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential



log = logging.getLogger(__name__)

EVENT_BUS_SOURCE = "fintracker.user-profile-service"


class EventBridgePublisher:
    """Outbound Adapter: publishes integration events to AWS EventBridge."""

    def __init__(self, event_bus_name: str) -> None:
        self._client = boto3.client("events")
        self._bus_name = event_bus_name

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def publish_user_deleted(self, user_id: UUID) -> None:
        """
        Emits a UserAccountDeleted event.
        Consumed by ledger-service to asynchronously purge financial records.
        """
        try:
            self._client.put_events(Entries=[{
                "Source": EVENT_BUS_SOURCE,
                "DetailType": "UserAccountDeleted",
                "EventBusName": self._bus_name,
                "Detail": json.dumps({"user_id": str(user_id)}),
            }])
            log.info("Published UserAccountDeleted event. user_id=%s", user_id)
        except ClientError as exc:
            log.error("Failed to publish UserAccountDeleted. user_id=%s error=%s", user_id, exc)
            raise
