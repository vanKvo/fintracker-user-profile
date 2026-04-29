"""
Inbound Adapter: Cognito Post-Confirmation Lambda Trigger (Workflows 1.1).

Invoked by Cognito after a user confirms their email (native registration)
or signs in with Google for the first time (federated identity).

Creates the IDENTITY mapping and initial PROFILE + SETTINGS records atomically.
"""
from __future__ import annotations

import logging

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from app.core.container import service

logger = Logger(service="user-profile-service")


@logger.inject_lambda_context(log_event=False)
def handler(event: dict, context: LambdaContext) -> dict:
    """
    Cognito trigger contract: must return the event unchanged on success.
    Raising an exception will block the user from being confirmed.
    """
    user_attrs = {attr["Name"]: attr["Value"]
                  for attr in event["request"]["userAttributes"]}

    cognito_sub = user_attrs["sub"]
    email       = user_attrs["email"]
    first_name  = user_attrs.get("given_name", "")
    last_name   = user_attrs.get("family_name", "")

    profile = service.register_user(
        cognito_sub=cognito_sub,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )

    logger.info("Post-confirmation complete", extra={
        "user_id": str(profile.user_id),
        "email": profile.email,
    })

    # Cognito requires the original event to be returned
    return event
