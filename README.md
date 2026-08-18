# Agentic GenAI Maintenance Copilot

A compact, production-oriented Agentic GenAI maintenance copilot for a simulated rotating-equipment environment.

The system is designed to help maintenance technicians investigate equipment issues, gather evidence, develop grounded diagnoses, recommend actions, and manage human-approved application actions.

## Project Status

Current version: **V0 — Foundation**

Implemented:

- Python 3.11 isolated environment
- FastAPI application foundation
- Typed environment configuration
- Basic application logging
- `GET /health` endpoint
- OpenAPI and Swagger documentation
- Automated test setup with pytest
- Code formatting and linting with Ruff
- Reproducible dependency files

Agent, SQL, RAG, work-order, approval, UI, evaluation, Docker, and Azure capabilities are planned but are not yet implemented.

## Safety Boundary

This copilot does not directly control machinery, shut down equipment, or modify PLC parameters.

Read-only investigation tools may run autonomously. State-changing application actions must pass application-level human approval before execution.

## Planned Maintenance Workflow

```text
Investigate
    → Gather Evidence
    → Diagnose
    → Recommend
    → Human Approval
    → Act
```

## Primary Assets

- P-101 — Main Cooling Water Pump
- P-102 — Standby Cooling Water Pump
- P-201 — Process Transfer Pump
- M-101 — Induction Motor driving P-101

## Current Technology

- Python 3.11
- FastAPI
- Pydantic
- Pydantic Settings
- Uvicorn
- pytest
- Ruff

Additional technologies will be introduced only when required by their MVP version.

## Local Setup

Create the Conda environment:

```bash
conda env create --file environment.yml
conda activate MaintenanceCopilot
```

Create a local configuration file:

```bat
copy .env.example .env
```

Run the API:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Health endpoint: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Quality Checks

Run automated tests:

```bash
python -m pytest
```

Run formatting and lint checks:

```bash
python -m ruff format --check .
python -m ruff check .
```

## MVP Roadmap

- V0 — Foundation
- V1 — Industrial Data Layer
- V2 — Deterministic Tools
- V3 — GenAI and LangGraph Agent Core
- V4 — Grounded Maintenance Investigation
- V5 — Human-in-the-Loop Actions
- V6 — Application and Observability
- V7 — Evaluation and Reliability
- V8 — Docker and Azure

The MVP is complete only after V8 works end-to-end.