"""
Inbound Adapter: REST Lambda handler for profile and settings endpoints (Workflow 1.3).

API Gateway extracts the Cognito sub from the validated JWT and forwards it
via the requestContext.authorizer.claims.sub field.
"""
from __future__ import annotations

import json
import logging

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from app.core.container import service
from app.services.services import UserNotFoundError

logger = Logger(service="user-profile-service")


def _cognito_sub(event: dict) -> str:
    """Extracts the Cognito sub from API Gateway's JWT authorizer context."""
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]


def _ok(body: dict) -> dict:
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def _problem(status: int, title: str, detail: str) -> dict:
    """RFC 9457 Problem Detail response."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/problem+json"},
        "body": json.dumps({
            "type": f"https://fintracker.dev/problems/{title.lower().replace(' ', '-')}",
            "title": title,
            "status": status,
            "detail": detail,
        }),
    }


@logger.inject_lambda_context(log_event=False)
def get_profile_handler(event: dict, context: LambdaContext) -> dict:
    """GET /profile/settings — returns profile + settings for the authenticated user."""
    try:
        cognito_sub = _cognito_sub(event)
        profile, settings = service.get_profile_and_settings(cognito_sub=cognito_sub)

        return _ok({
            "userId": str(profile.user_id),
            "email": profile.email,
            "firstName": profile.first_name,
            "lastName": profile.last_name,
            "subscriptionTier": profile.subscription_tier.value,
            "settings": {
                "currency": settings.currency,
                "timezone": settings.timezone,
                "notificationPrefs": {
                    "channel": settings.notification_prefs.channel.value,
                    "budgetAlerts": settings.notification_prefs.budget_alerts,
                    "statementProcessed": settings.notification_prefs.statement_processed,
                },
            },
        })
    except UserNotFoundError as exc:
        logger.warning("Profile not found", extra={"error": str(exc)})
        return _problem(404, "User Not Found", str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in get_profile_handler")
        return _problem(500, "Internal Server Error", "An unexpected error occurred.")


@logger.inject_lambda_context(log_event=False)
def delete_account_handler(event: dict, context: LambdaContext) -> dict:
    """DELETE /profile — offboards the user and emits AccountDeleted event."""
    try:
        cognito_sub = _cognito_sub(event)
        service.delete_account(cognito_sub=cognito_sub)
        return {"statusCode": 204, "body": ""}
    except UserNotFoundError as exc:
        return _problem(404, "User Not Found", str(exc))
    except Exception:
        logger.exception("Unexpected error in delete_account_handler")
        return _problem(500, "Internal Server Error", "An unexpected error occurred.")
