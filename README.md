# User Profile Service

The User Profile Service manages user identity, preferences, savings goals, and real-time WebSocket connections. Built as a pure Serverless Python application, it leverages a Layered Architecture, AWS API Gateway, AWS Lambda, DynamoDB, and AWS Cognito.

## Key Features & Impacts
* **Identity Management:** Standardizes user identification via an internal UUID, decoupling the system from the external Cognito IdP and ensuring seamless future migrations.
* **Savings Goals & Preferences:** Manages personalized financial configurations and tracking targets, empowering users to monitor their "Safe to Spend" metrics.
* **Real-time Notifications:** Implements a WebSocket infrastructure that enables background workers (e.g., statement processors) to push instant, asynchronous updates to the client browser without polling overhead.
* **Automated Offboarding:** Orchestrates complete account deletion workflows by purging localized data and emitting integration events for downstream service cleanup.

## Architecture

This service strictly adheres to a Python Layered Architecture, decoupling API handlers, business logic, and database access.

```text
app/
├── api/             # API Layer (REST and WebSocket Lambda handlers)
│   └── v1/
│       └── endpoints/
├── core/            # Global configuration & Dependency Injection container
├── crud/            # Data Access Layer (DynamoDB Repositories)
├── schemas/         # Pydantic models & Data Transfer Objects
└── services/        # Core Business Logic & EventBridge Publishers
```
*(Diagrams and global architecture details can be found in `/docs/fintracker-architectural-doc.md`)*

## Tech Stack
Frontend:	Angular (via fintracker-ui)
Backend:	Python (Lambda Handlers)
Cloud:		AWS (Lambda, DynamoDB, Cognito, EventBridge, API Gateway)
DevOps:		Poetry, pytest

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
| AWS Cognito | Post-Confirmation | Fires after email confirmation or initial OAuth login to initialize the user's DynamoDB profile. |
| API Gateway | WebSocket `$connect` | Authorizes the user and stores their WebSocket connection ID and endpoint. |
| API Gateway | WebSocket `$disconnect` | Cleans up the disconnected WebSocket session from DynamoDB. |

## Core Workflows

* **Identity Mapping Initialization:** Upon Cognito's Post-Confirmation trigger, the service atomically writes an `IDENTITY` mapping alongside `PROFILE` and `SETTINGS` rows in DynamoDB. This transaction uses conditional expressions to ensure idempotency.
* **Account Offboarding:** Account deletion requests trigger a BatchWrite to erase all DynamoDB rows associated with the user. The service then emits a `UserAccountDeleted` event to EventBridge, allowing downstream systems like the Ledger Service to asynchronously purge financial records.

## Quick Start
<details>
<summary>Click to expand setup instructions</summary>

### Prerequisites
* Python 3.12+
* Poetry
* AWS CLI

### Installation
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/vanKvo/fintracker.git
    cd fintracker/services/fintracker-user-profile
    ```
2.  **Configure Environment:**
    Ensure the following environment variables are set for local testing:
    ```bash
    export DYNAMODB_TABLE_NAME="FinTracker_UserProfile"
    export EVENT_BUS_NAME="fintracker-custom-bus"
    ```
3.  **Install Dependencies:**
    ```bash
    poetry install
    ```
4.  **Run Tests:**
    ```bash
    poetry run pytest tests/
    ```

</details>
