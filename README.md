# User Profile Service

The User Profile Service manages user identity, preferences, savings goals, and real-time WebSocket connections. It is built as a pure Serverless Python application using Hexagonal Architecture, AWS API Gateway, AWS Lambda, DynamoDB, and AWS Cognito.

## Architecture

- This service follows the **Hexagonal Architecture (Ports & Adapters)** pattern. The pure Python domain layer (dataclasses and services) contains zero infrastructure dependencies or AWS SDK imports. All infrastructure concerns (DynamoDB, EventBridge, API Gateway request extraction) are pushed to the outermost adapter layer and injected via a Dependency Injection container.

```
src/
  domain/
    models.py       # Frozen dataclasses (UserProfile, UserSettings, SavingsGoal, WebSocketConnection)
    ports.py        # Abstract Base Classes (UserRepository, GoalRepository, WebSocketRepository, EventPublisher)
    services.py     # Pure business logic — zero AWS dependencies
  infrastructure/
    dynamodb_repository.py    # DynamoDB Outbound Adapters (boto3)
    eventbridge_publisher.py  # EventBridge Outbound Adapter
  app/
    post_confirmation_handler.py  # Cognito Post-Confirmation trigger (Inbound)
    profile_handler.py            # REST Lambdas: GET /profile/settings, DELETE /profile
    goals_handler.py              # REST Lambdas: GET/POST/DELETE /profile/goals
    websocket_handler.py          # WebSocket Lambdas: $connect, $disconnect
  config/
    container.py    # DI wiring — binds adapters to ports at cold-start
```

## Modules & Interfaces

**REST API Operations**

| Module | Method | Path | Description |
|---|---|---|---|
| Profile | `GET` | `/profile/settings` | Fetches the unified user profile and notification settings. |
| Profile | `DELETE` | `/profile` | Initiates the account offboarding workflow. |
| Goals | `GET` | `/profile/goals` | Lists all savings goals for the user. |
| Goals | `POST` | `/profile/goals` | Creates a new savings goal. |
| Goals | `DELETE` | `/profile/goals/{id}` | Deletes a specific savings goal. |

**Event-Driven / Serverless Triggers**

| Event Source | Trigger/Pattern | Description |
|---|---|---|
| AWS Cognito | Post-Confirmation Trigger | Fires after native email confirmation or initial Google OAuth login to initialize the user's DynamoDB profile and mapping. |
| API Gateway | WebSocket `$connect` | Authorizes the user and stores their WebSocket connection ID and endpoint. |
| API Gateway | WebSocket `$disconnect` | Cleans up the disconnected WebSocket session from DynamoDB. |

## Core Workflows

**Identity Mapping Initialization**
When Cognito fires the Post-Confirmation trigger, the domain service orchestrates the creation of a standard internal UUID (`user_id`). The DynamoDB repository uses an atomic `TransactWriteItems` operation to store an `IDENTITY#<cognito_sub>` mapping alongside the core `PROFILE` and `SETTINGS` rows. This transaction includes a `ConditionExpression: attribute_not_exists(PK)` on the identity row to guarantee idempotency if Cognito retries the trigger.

**Account Offboarding**
When a user requests account deletion, the Lambda queries all DynamoDB rows beginning with the partition key `USER#<user_id>` and deletes them via a `BatchWrite`. It then publishes a `UserAccountDeleted` event to AWS EventBridge. Downstream services (like the Ledger Service) listen to this event and asynchronously obliterate their localized tenant data, decoupling the profile cleanup from financial ledger cleanup.

## Local Setup

### Prerequisites
- Python 3.12+
- Poetry
- AWS CLI

### Run Locally
To set up dependencies, use Poetry to initialize the virtual environment:
```bash
poetry install
```

When deploying or testing locally (e.g., using AWS SAM local or Moto), ensure you export the following variables:
```bash
export DYNAMODB_TABLE_NAME="FinTracker_UserProfile"
export EVENT_BUS_NAME="fintracker-custom-bus"
```

### Build & Test
Run the automated test suite using `pytest`. The domain layer is tested in 100% isolation using `unittest.mock`.
```bash
poetry run pytest tests/
poetry run ruff check src/
poetry run mypy src/
```

## Key Design Decisions

- **Identity Mapping Pattern**: The internal domain standardizes on its own internal `user_id` standard UUID type. The external Cognito `sub` is strictly isolated to the mapping boundary table logic. If we ever migrate IdPs (e.g. from Cognito to Auth0), we only need to update the mapping row rather than cascading schema changes across all distributed microservices.
- **Single-Table Design**: User Profiles, Settings, Savings Goals, and ephemeral WebSocket connections all reside within a single DynamoDB table utilizing generic `PK` and `SK` patterns (e.g., `PK=USER#<uuid>`, `SK=GOAL#<uuid>`). This ensures extremely fast partitioned lookups.
- **Cold-Start Optimization**: Lightweight dependency injection is implemented statically inside `config/container.py` when the Lambda container spins up. The business logic executes rapidly on hot invocations since all wiring was completed at the module load level.
- **Push over Pull**: Using API Gateway WebSocket Connections allows background workers (e.g., statement processors or analytics engines) to trigger a Boto3 `PostToConnection` API call, instantly pushing state updates to the browser without requiring the UI to maintain frequent HTTP polling sequences.
