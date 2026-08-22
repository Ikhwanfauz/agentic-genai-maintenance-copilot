# Agentic GenAI Maintenance Copilot

A compact, production-oriented Agentic GenAI maintenance copilot for a simulated rotating-equipment environment.

The system is designed to help maintenance technicians investigate equipment issues, gather evidence, develop grounded diagnoses, recommend actions, and manage human-approved application actions.

## Project Status

Current version: **V4.1 - Typed Evidence Ledger**

Implemented:

- Python 3.11 isolated environment
- FastAPI application foundation and `GET /health`
- Typed environment configuration and application logging
- SQLAlchemy models, SQLite database, and Alembic migrations
- Deterministic industrial-data seeding
- Read-only asset, maintenance-history, sensor-analysis, and RAG tools
- Pydantic tool input and output contracts
- Local Sentence Transformers embeddings and persistent Chroma storage
- Structured evidence citations
- Hosted LLM provider abstraction for OpenAI and Azure OpenAI
- Azure OpenAI v1 integration using `gpt-5.4-mini`
- Typed LangGraph agent state
- Bounded model-tool-model iteration loop
- Structured tool binding with parallel tool calls disabled
- Deterministic tool execution through application-owned adapters
- Structured `MaintenanceDiagnosis` output
- Evidence-aware insufficient-evidence behavior
- Application-owned typed evidence ledger
- Deterministic citation capture from all four read-only investigation tools
- Automated tests with pytest
- Code formatting and linting with Ruff

Manual hosted validation has confirmed direct Azure inference, real model tool
selection, SQLite-backed tool execution, bounded LangGraph routing, structured
diagnosis generation, citation capture, and evidence-based abstention.

V4 evidence-coverage policy and grounded-synthesis enforcement, V5 human-approved
actions, agent REST endpoints, Streamlit UI, persisted observability, evaluation,
Docker, and Azure application deployment are not yet implemented.

## Safety Boundary

This copilot does not directly control machinery, shut down equipment, modify PLC
parameters, or bypass equipment interlocks.

All V3 investigation tools are read-only. LangGraph controls routing and bounded
iteration, while application-owned Python adapters execute deterministic SQL,
sensor-analysis, and RAG operations.

The structured diagnosis contract supports an `insufficient_evidence` outcome so
the agent can abstain instead of inventing a fault or root cause.

V4.1 additionally captures successful read-only tool outputs in a typed evidence
ledger owned by the application. Asset, maintenance-record, sensor-metric, and
engineering-document evidence receive traceable citations before later synthesis
enforcement is introduced.

Creating a proposed work order does not authorize physical maintenance.
Application-level approval enforcement, duplicate-action protection, and
LangGraph pause/resume behavior will be implemented in V5.

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

The deterministic seed process creates:

| Data type | Records |
|---|---:|
| Assets | 4 |
| Maintenance records | 7 |
| Sensor readings | 2,520 |
| Work orders | 2 |
| Approvals | 2 |

The sensor dataset contains seven days of hourly readings.

P-101 and M-101 contain correlated degradation trends in vibration, temperature, flow, pressure, and motor current. Stable comparison assets and known data-quality issues are included for deterministic tool development and evaluation.

All sensor data is synthetic and must not be interpreted as live industrial telemetry.

## V2 Deterministic Tools

### `get_asset_details()`

Retrieves structured asset information, including:

- Equipment identity
- Type and operating status
- Criticality
- Location and manufacturer
- Parent and child asset relationships

### `query_maintenance_history()`

Retrieves maintenance records with bounded filtering by:

- Asset code
- Maintenance type
- Start and end time
- Result limit

Results are ordered from newest to oldest and indicate whether additional matching records exist.

### `analyze_sensor_data()`

Performs deterministic sensor analysis including:

- Data-quality accounting
- Bad and suspect reading exclusion
- Minimum, maximum, and mean values
- Early-window and recent-window comparison
- Percentage change
- Linear-regression slope
- Increasing, decreasing, or stable trend classification

The relative trend threshold is an analytical heuristic, not an equipment trip, shutdown, or safety threshold.

### `search_engineering_docs()`

Performs semantic retrieval over synthetic engineering documents using:

- `sentence-transformers/all-MiniLM-L6-v2`
- 384-dimensional normalized embeddings
- Persistent Chroma vector storage
- Optional asset filtering
- Bounded top-k retrieval
- Minimum relevance filtering
- Structured source citations

The search tool retrieves engineering evidence. It does not independently generate a diagnosis.

## V3 GenAI and LangGraph Agent Core

V3 introduces a single stateful LangGraph investigation agent with:

- A hosted-model provider abstraction
- Azure OpenAI v1 API integration
- Typed agent state and explicit routing
- Bounded model-tool-model loops
- One tool call per iteration
- Parallel tool calls disabled
- Application-owned tool execution
- Structured diagnosis synthesis
- Pydantic validation
- Evidence citations
- Insufficient-evidence outcomes

The selected development deployment is `gpt-5.4-mini` using Azure Data Zone
Standard in the APAC data zone. The model is configured through environment
variables and can be replaced without redesigning the graph or deterministic
tool layer.

Hosted smoke tests are run manually so the normal automated test suite does not
make billable external model calls.

## V4.1 Typed Evidence Ledger

V4.1 begins the grounded maintenance-investigation layer by converting successful
deterministic tool results into typed `CollectedEvidence` records stored in the
LangGraph state.

The ledger captures:

- Asset evidence with `asset:<asset-code>` citations
- Individual maintenance records with `maintenance_record:<record-id>` citations
- Individual sensor metrics with `sensor:<asset-code>:<sensor-type>` citations
- Engineering-document chunks with their original RAG citations preserved

Failed tool messages are not accepted as evidence. Final diagnosis citation
validation against this ledger belongs to a later V4 checkpoint and is not claimed
as part of V4.1.

## Engineering Document Corpus

The V2 corpus contains three original synthetic documents:

- Centrifugal Pump Troubleshooting Guide
- Motor and Pump Alignment Maintenance Guide
- Maintenance Investigation and Work-Order Safety Procedure

The documents are split into nine section-level chunks. Each chunk has a stable ID and metadata containing its document ID, title, section, source path, and applicable assets.

The generated Chroma index is not committed to Git because it can be reproduced from the source documents.

## Database Schema

Application tables:

- `assets`
- `sensor_readings`
- `maintenance_records`
- `work_orders`
- `approvals`
- `agent_runs`
- `agent_steps`
- `tool_calls`

Alembic maintains the `alembic_version` table to track the active database revision.

## Current Technology

- Python 3.11
- FastAPI
- Pydantic and Pydantic Settings
- Uvicorn
- SQLAlchemy 2.0
- Alembic
- SQLite
- ChromaDB
- Sentence Transformers
- LangGraph
- LangChain OpenAI
- Microsoft Foundry / Azure OpenAI
- pytest
- Ruff

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
|-- rag/
|   |-- documents.py
|   |-- embeddings.py
|   `-- indexer.py
|-- schemas/
|   |-- asset.py
|   |-- common.py
|   |-- maintenance.py
|   |-- rag.py
|   `-- sensor.py
|-- tools/
|   |-- asset.py
|   |-- exceptions.py
|   |-- maintenance.py
|   |-- rag.py
|   `-- sensor.py
`-- main.py

data/
|-- engineering_docs/
`-- .gitkeep

migrations/
tests/
```

## Local Setup

Create and activate the Conda environment:

```bash
conda env create --file environment.yml
conda activate MaintenanceCopilot
```

If the environment already exists:

```bash
python -m pip install -r requirements-dev.txt
```

Create a local configuration file:

```bat
copy .env.example .env
```

For Azure OpenAI, configure the local `.env` file:

```text
LLM_PROVIDER=azure_openai
LLM_MODEL=gpt-5.4-mini
LLM_REASONING_EFFORT=low
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini
```

The endpoint may be supplied either as the Azure resource endpoint or with the
`/openai/v1/` suffix. Never commit the populated `.env` file or expose its API
key.

Apply the latest database migration:

```bash
python -m alembic upgrade head
```

Seed the simulated industrial dataset:

```bash
python -m app.db.seed
```

The SQL seed command is idempotent. Running it again detects the existing complete dataset instead of creating duplicate records.

Index the engineering-document corpus:

```bash
python -m app.rag.indexer
```

The RAG indexing command uses stable chunk IDs and Chroma upserts, so repeated indexing does not duplicate chunks.

## Run the API

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Health endpoint: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

V2 tools are currently Python application functions. REST endpoints for maintenance investigations will be introduced in later application versions.

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

Check dependency compatibility:

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
- V2 - Deterministic Tools: complete
- V3 - GenAI and LangGraph Agent Core: complete
- V4 - Grounded Maintenance Investigation: in progress (V4.1 complete)
- V5 - Human-in-the-Loop Actions
- V6 - Application and Observability
- V7 - Evaluation and Reliability
- V8 - Docker and Azure

The MVP is complete only after V8 works end-to-end.
