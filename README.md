# Agentic GenAI Maintenance Copilot

A compact, production-oriented Agentic GenAI maintenance copilot for a simulated rotating-equipment environment.

The system is designed to help maintenance technicians investigate equipment issues, gather evidence, develop grounded diagnoses, recommend actions, and manage human-approved application actions.

## Project Status

Current version: **V5 - Human-in-the-Loop Actions Complete**

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
- Deterministic multi-source evidence-coverage policy
- Asset-scoped coverage decisions with cross-asset evidence exclusion
- Application-owned citation allowlist for structured synthesis
- Deterministic diagnosis-reference validation and fail-closed abstention
- Structured grounding audit result in LangGraph state
- End-to-end grounded investigation scenarios with real SQLite and Chroma tools
- Verified incomplete-evidence, tool-failure, out-of-scope, and no-mutation behavior
- Grounded work-order proposal contracts
- Deterministic work-order and pending-approval persistence
- Proposal idempotency and conflicting-payload protection
- Typed human approval and rejection contracts
- Deterministic approval state-transition enforcement
- Approval revision, scope, expiry, and conflict guards
- Native LangGraph human-in-the-loop interrupts
- Typed approval pause and resume payloads
- Durable SQLite-backed LangGraph checkpointing
- Strict checkpoint deserialization with Pydantic revalidation
- Correctable re-interrupt behavior for invalid resume payloads
- End-to-end approved and rejected work-order journeys
- Application-level approval without physical execution
- Automated tests with pytest
- Code formatting and linting with Ruff
- 146 automated tests at the verified V5 checkpoint

Manual hosted validation has confirmed direct Azure inference, real model tool
selection, SQLite-backed tool execution, bounded LangGraph routing, structured
diagnosis generation, citation capture, and evidence-based abstention.

V5 human-approved application actions are complete. Agent REST endpoints,
Streamlit UI, persisted runtime observability, evaluation, Docker, and Azure
application deployment remain assigned to V6-V8.

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

Creating or approving a proposed work order does not authorize or record physical
maintenance execution. V5 enforces application-level human approval, duplicate-
proposal protection, version and scope validation, durable LangGraph pause/resume,
and fail-closed resume identity checks.

An approved work order remains unexecuted: `executed_at`,
`execution_summary`, and approval `consumed_at` remain unset. No V5 component
controls machinery, modifies PLC parameters, bypasses interlocks, or reports that
physical work occurred.

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

## V4.2 Evidence Coverage and Investigation Policy

V4.2 adds a deterministic policy that evaluates whether the evidence ledger
contains the minimum source categories for one asset-scoped investigation:

- Asset details
- Maintenance history
- Sensor analysis
- Engineering-document guidance

The policy returns `ready`, `incomplete`, or `asset_scope_required`, together with
covered and missing source categories. Evidence belonging to another asset is
excluded from the target asset's coverage result. The policy is evaluated when an
investigation becomes ready and recalculated after every tool execution.

Evidence coverage only confirms that the required source categories are
represented. It does not prove a root cause, validate model claims against
citations, or authorize an application action. Those boundaries remain assigned to
later checkpoints.

## V4.3 Grounded Synthesis Enforcement

V4.3 supplies structured synthesis with an application-owned citation allowlist
containing only evidence metadata eligible for the target asset. A claimed
diagnosis is accepted only when:

- Evidence coverage is `ready` for the investigation target
- The diagnosis asset matches the target asset
- Every evidence reference exactly matches an eligible source type, source ID, and
  citation
- The diagnosis references every required evidence source category
- Evidence references are not duplicated

If any rule fails, the application replaces the claimed diagnosis with a
low-confidence `insufficient_evidence` result and stores a structured grounding
audit containing matched citations and validation violations. Model-selected
`insufficient_evidence` and `out_of_scope` results remain supported.

This enforcement validates provenance, citation identity, source coverage, and
asset scope. It does not claim deterministic semantic proof that every natural-
language sentence is entailed by an evidence payload; that limitation remains
explicit for truthful portfolio reporting.

## V4.4 End-to-End Grounded Investigation Scenarios

V4.4 validates the complete V4 workflow through LangGraph using deterministic fake
models and real local application integrations. The scenario suite covers:

- A complete P-101 investigation that sequentially executes all four real read-only
  tools and returns a grounded structured diagnosis
- An incomplete investigation whose claimed diagnosis is downgraded to
  `insufficient_evidence`
- A controlled real-tool failure whose output is excluded from the evidence ledger
  and ends in safe abstention
- An out-of-scope request that completes without tool execution
- SQL and Chroma record-count checks before and after every scenario to prove the
  investigation workflow remains read-only

The tests use the deterministic seeded industrial dataset, a temporary file-backed
SQLite database, an ephemeral Chroma collection, the synthetic engineering corpus,
and the application-owned tool adapters. Fake models avoid billable hosted calls
while preserving the real model-tool-model graph transitions and structured
synthesis boundary.

## V5 Human-in-the-Loop Actions

V5 extends the grounded investigation workflow with application-level work-order
proposals and explicit human approval. The model may recommend an eligible action,
but deterministic application code owns proposal creation, database mutation,
approval enforcement, checkpoint persistence, and resume validation.

### V5.1 Grounded Work-Order Proposals

A work-order proposal is accepted only when the source diagnosis:

- Has a completed `diagnosis` outcome
- Matches the proposal asset
- Passed application-owned grounding enforcement
- Was not downgraded
- Contains no grounding violations
- Uses citations that exactly match the grounding audit

The proposal service writes a `pending_approval` work order and a matching
`pending` approval request in one transaction. Stable idempotency keys return the
existing proposal for identical retries and reject conflicting payloads.

### V5.2 Human Approval Enforcement

Typed human decisions support only `approved` or `rejected`. The deterministic
approval service verifies:

- Work-order and approval-record identity
- Current request revision
- Approval scope
- Pending state
- Optional expiry
- Human decision metadata
- Conflicting or repeated decisions

An identical retry returns the existing decision. A conflicting second decision is
rejected without replacing the first decision.

### V5.3 Durable LangGraph Pause and Resume

The main LangGraph agent can pause after a grounded work-order proposal using a
native dynamic interrupt. The interrupt contains a typed, JSON-serializable
proposal payload.

The graph uses a stable `thread_id` and an official SQLite checkpointer. Automated
tests close the original checkpoint connection, construct a new saver and graph,
and resume the same workflow from the persisted checkpoint.

Strict checkpoint deserialization is enabled explicitly. Restored plain data is
revalidated through Pydantic before it is trusted as application state.

### V5.4 End-to-End HITL Safety

The V5 end-to-end scenarios use fake models with real SQLite application records,
real proposal and approval services, durable LangGraph checkpoints, and native
resume commands. They verify:

- Complete grounded evidence can create one pending proposal
- Approved and rejected human journeys update the correct records
- Resume does not repeat model inference or proposal mutation
- Insufficient evidence creates no work-order or approval records
- Tampered run, thread, work-order, approval, version, and scope data is rejected
- Invalid resume input produces a correctable re-interrupt
- Approved work remains application-approved but physically unexecuted

Automated tests do not make billable hosted-model calls.

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
- LangGraph SQLite Checkpointer
- LangChain OpenAI
- Microsoft Foundry / Azure OpenAI
- pytest
- Ruff

## Repository Structure

```text
app/
|-- agent/
|   |-- approval.py
|   |-- checkpoint.py
|   |-- evidence.py
|   |-- graph.py
|   |-- grounding.py
|   |-- nodes.py
|   |-- policy.py
|   |-- proposal.py
|   |-- state.py
|   |-- synthesis.py
|   `-- tool_node.py
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
|-- llm/
|-- models/
|-- rag/
|-- schemas/
|   |-- actions.py
|   |-- diagnosis.py
|   |-- evidence.py
|   |-- hitl.py
|   |-- investigation.py
|   `-- tool-specific schemas
|-- services/
|   |-- approvals.py
|   |-- exceptions.py
|   `-- work_orders.py
|-- tools/
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

The investigation, proposal, approval, and resume workflows currently operate as
Python application components. REST endpoints for these workflows are assigned to
V6.

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
- V4 - Grounded Maintenance Investigation: complete
- V5 - Human-in-the-Loop Actions: complete
- V6 - Application and Observability
- V7 - Evaluation and Reliability
- V8 - Docker and Azure

The MVP is complete only after V8 works end-to-end.
