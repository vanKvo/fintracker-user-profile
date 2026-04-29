"""
Inbound Adapter: REST Lambda handler for Savings Goals CRUD (Workflow 1.5).

GET  /profile/goals        → list_goals
POST /profile/goals        → create_goal
DELETE /profile/goals/{id} → delete_goal
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from config.container import service
from domain.services import UserNotFoundError

logger = Logger(service="user-profile-service")


def _cognito_sub(event: dict) -> str:
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]


def _ok(body) -> dict:
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def _created(body) -> dict:
    return {"statusCode": 201, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def _problem(status: int, title: str, detail: str) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/problem+json"},
            "body": json.dumps({"type": "https://fintracker.dev/problems/goals",
                                 "title": title, "status": status, "detail": detail})}


@logger.inject_lambda_context(log_event=False)
def goals_handler(event: dict, context: LambdaContext) -> dict:
    method = event["requestContext"]["http"]["method"]
    try:
        cognito_sub = _cognito_sub(event)
        if method == "GET":
            goals = service.list_goals(cognito_sub=cognito_sub)
            return _ok([_serialize(g) for g in goals])

        if method == "POST":
            body = json.loads(event.get("body") or "{}")
            goal = service.create_goal(
                cognito_sub=cognito_sub,
                goal_name=body["goalName"],
                target_amount=float(body["targetAmount"]),
                current_amount=float(body.get("currentAmount", 0)),
                deadline=datetime.fromisoformat(body["deadline"]) if body.get("deadline") else None,
            )
            return _created(_serialize(goal))

    except UserNotFoundError as exc:
        return _problem(404, "User Not Found", str(exc))
    except KeyError as exc:
        return _problem(400, "Bad Request", f"Missing required field: {exc}")
    except Exception:
        logger.exception("Unexpected error in goals_handler")
        return _problem(500, "Internal Server Error", "An unexpected error occurred.")


@logger.inject_lambda_context(log_event=False)
def delete_goal_handler(event: dict, context: LambdaContext) -> dict:
    try:
        cognito_sub = _cognito_sub(event)
        goal_id = UUID(event["pathParameters"]["id"])
        service.delete_goal(cognito_sub=cognito_sub, goal_id=goal_id)
        return {"statusCode": 204, "body": ""}
    except UserNotFoundError as exc:
        return _problem(404, "User Not Found", str(exc))
    except Exception:
        logger.exception("Unexpected error in delete_goal_handler")
        return _problem(500, "Internal Server Error", "An unexpected error occurred.")


def _serialize(goal) -> dict:
    return {
        "goalId": str(goal.goal_id),
        "goalName": goal.goal_name,
        "targetAmount": goal.target_amount,
        "currentAmount": goal.current_amount,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
    }
