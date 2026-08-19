# Agentic GenAI Maintenance Copilot

A compact, production-oriented Agentic GenAI maintenance copilot for a simulated rotating-equipment environment.

The system is designed to help maintenance technicians investigate equipment issues, gather evidence, develop grounded diagnoses, recommend actions, and manage human-approved application actions.

## Project Status

Current version: **V1 - Industrial Data Layer**

Implemented:

- Python 3.11 isolated environment
- FastAPI application foundation
- Typed environment configuration
- Basic application logging
- `GET /health` endpoint
- SQLAlchemy 2.0 data models
- SQLite development database
- Alembic schema migrations
- Asset and maintenance-history records
- Synthetic time-series sensor readings
- Work-order and persisted approval schemas
- Agent-run, agent-step, and tool-call logging schemas
- Deterministic and idempotent database seeding
- Automated tests with pytest
- Code formatting and linting with Ruff

The deterministic maintenance tools, RAG pipeline, LLM integration, LangGraph agent, user interface, and cloud deployment are not yet implemented.

## Safety Boundary

This copilot does not directly control machinery, shut down equipment, or modify PLC parameters.

Read-only investigation tools may run autonomously. State-changing application actions must pass application-level human approval before execution.

V1 defines the work-order and approval persistence schemas. Approval enforcement and agent pause/resume behavior will be implemented in V5.

## Planned Maintenance Workflow

```text
Investigate
    -> Gather Evidence
    -> Diagnose
    -> Recommend
    -> Human Approval
    -> Act
```

## Primary Assets

- P-101 - Main Cooling Water Pump
- P-102 - Standby Cooling Water Pump
- P-201 - Process Transfer Pump
- M-101 - Induction Motor driving P-101

## V1 Industrial Dataset

The seed process creates a deterministic simulated maintenance environment containing:

| Data type | Records |
|---|---:|
| Assets | 4 |
| Maintenance records | 7 |
| Sensor readings | 2,520 |
| Work orders | 2 |
| Approvals | 2 |

The sensor dataset contains seven days of hourly readings.

P-101 and M-101 contain correlated degradation trends in vibration, temperature, flow, pressure, and motor current. Stable comparison assets and known data-quality issues are also included for deterministic tool development and evaluation.

All sensor data is synthetic and must not be interpreted as live industrial telemetry.

## Database Schema

V1 introduces these application tables:

- `assets`
- `sensor_readings`
- `maintenance_records`
- `work_orders`
- `approvals`
- `agent_runs`
- `agent_steps`
- `tool_calls`

Alembic also maintains the `alembic_version` table to track the active database revision.

## Current Technology

- Python 3.11
- FastAPI
- Pydantic
- Pydantic Settings
- Uvicorn
- SQLAlchemy 2.0
- Alembic
- SQLite
- pytest
- Ruff

Additional technologies will be introduced only when required by their MVP version.

## Repository Structure

```text
app/
|-- api/
|   `-- routes/
|       `-- health.py
|-- core/
|   |-- config.py
|   `-- logging.py
|-- db/
|   |-- base.py
|   |-- session.py
|   |-- seed.py
|   |-- seed_reference.py
|   `-- seed_sensor.py
|-- models/
|   |-- agent_log.py
|   |-- approval.py
|   |-- asset.py
|   |-- common.py
|   |-- enums.py
|   |-- maintenance.py
|   |-- sensor.py
|   `-- work_order.py
`-- main.py

migrations/
tests/
data/
```

## Local Setup

Create and activate the Conda environment:

```bash
conda env create --file environment.yml
conda activate MaintenanceCopilot
```

If the environment already exists, install or update the dependencies with:

```bash
python -m pip install -r requirements-dev.txt
```

Create a local configuration file:

```bat
copy .env.example .env
```

Apply the latest database migration:

```bash
python -m alembic upgrade head
```

Seed the simulated industrial dataset:

```bash
python -m app.db.seed
```

The seed command is idempotent. Running it again detects the existing complete dataset instead of creating duplicate records.

## Run the API

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Health endpoint: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Quality Checks

Format the code:

```bash
python -m ruff format .
```

Run lint checks:

```bash
python -m ruff check .
```

Run automated tests:

```bash
python -m pytest
```

Check installed dependency compatibility:

```bash
python -m pip check
```

## Database Migration Commands

Show the current migration:

```bash
python -m alembic current
```

Show migration history:

```bash
python -m alembic history
```

Upgrade to the latest schema:

```bash
python -m alembic upgrade head
```

Downgrade all project migrations:

```bash
python -m alembic downgrade base
```

Downgrading removes application tables and their stored data. Use it only against a disposable or backed-up database.

## MVP Roadmap

- V0 - Foundation: complete
- V1 - Industrial Data Layer: complete
- V2 - Deterministic Tools
- V3 - GenAI and LangGraph Agent Core
- V4 - Grounded Maintenance Investigation
- V5 - Human-in-the-Loop Actions
- V6 - Application and Observability
- V7 - Evaluation and Reliability
- V8 - Docker and Azure

The MVP is complete only after V8 works end-to-end.