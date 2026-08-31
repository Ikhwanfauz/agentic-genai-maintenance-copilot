# Agentic GenAI Maintenance Copilot

A compact, production-oriented Agentic GenAI maintenance copilot for a simulated rotating-equipment environment.

The system is designed to help maintenance technicians investigate equipment issues, gather evidence, develop grounded diagnoses, recommend actions, and manage human-approved application actions.

## Project Status

Current version: **V8.4 - Hosted Azure Application Validation Complete**

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
- Typed REST contracts for investigation, run status, and human decisions
- Persisted agent-run lifecycle and approval-resume workflow services
- FastAPI investigation, run-status, and approval endpoints
- Lazy production agent-runtime initialization
- Durable SQLite-backed runtime and checkpoint recovery
- Persisted agent-step, tool-call, and model-usage observability
- Real provider token-usage aggregation without fabricated cost estimates
- Explicit trusted-type allowlist for strict checkpoint deserialization
- Typed HTTPX2 client for the operator application
- Streamlit investigation and human-approval dashboard
- Revalidated Streamlit session state and stale-approval protection
- Typed and versioned evaluation scenario contracts
- Validated JSON evaluation-dataset loading
- Balanced 15-scenario core evaluation dataset
- Normal, degraded, contradictory, insufficient-evidence, and adversarial taxonomy
- Strict machine-readable deterministic evaluation results
- Outcome, evidence, citation, tool, claim, safety, and trajectory scorers
- Fail-closed proposal, approval, and physical-execution evaluation boundaries
- Deterministic fixture registry and scripted model responses
- Asset-scoped evaluation failure injection
- Fresh isolated SQLite, Chroma, and checkpoint environments per scenario
- Real LangGraph execution across all 15 core evaluation scenarios
- Machine-readable JSON regression reports
- Command-line deterministic evaluation runner
- GitHub Actions Docker build and container-health smoke-test gate
- Cross-platform Ruff import classification
- Non-root Docker image with CPU-only PyTorch dependencies
- Idempotent Alembic, seed-data, and RAG-index container initialization
- Docker Compose orchestration for the API and Streamlit dashboard
- Persistent runtime storage with container health and secret-isolation boundaries
- Automated tests with pytest
- Code formatting and linting with Ruff
- 529 automated tests at the verified V8.4 checkpoint

Manual hosted validation has confirmed direct Azure inference, real model tool
selection, SQLite-backed tool execution, bounded LangGraph routing, structured
diagnosis generation, citation capture, evidence-based abstention, REST delivery,
Streamlit rendering, persisted observability, and checkpoint recovery after an
application restart.

An earlier V6 hosted dashboard journey completed one grounded P-101
investigation using `gpt-5.4-mini`. It recorded 6 model calls, 10,135 provider-
reported tokens, 13 completed graph steps, four successful read-only tool calls,
and 11 diagnosis citations in 28.147 seconds. Estimated cost remains `0.0`
because the application does not fabricate pricing data.

That earlier hosted run completed without a work-order proposal because its
recommended action was not marked state-changing. V8.4 corrected the inspection
classification behavior and revalidated the complete hosted human-in-the-loop
journey through proposal, approval, workflow resume, and completion.

V6 application delivery and persisted observability are complete. V7 evaluation
and reliability are complete. V7.1 establishes the typed evaluation
contracts and versioned core scenario dataset. V7.2 adds pure deterministic
scorers with machine-readable pass/fail results. V7.3 executes all 15 scenarios
through the real LangGraph workflow using deterministic scripted models, isolated
SQLite and Chroma environments, controlled failure injection, and machine-readable
JSON regression reports. V7.4 adds a GitHub Actions quality gate that verifies
dependency compatibility, formatting, linting, and all automated tests on Ubuntu.
V7 is complete. V8 completes containerization, container quality gates, Azure
infrastructure, Azure application deployment, and hosted end-to-end validation.

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
`execution_summary`, and approval `consumed_at` remain unset. No application or
operator-interface component controls machinery, modifies PLC parameters,
bypasses interlocks, or reports that physical work occurred.

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

## V6 Application and Observability

V6 exposes the grounded LangGraph workflow through typed application services,
REST endpoints, persisted runtime telemetry, and a Streamlit operator interface.
The API and UI do not weaken the deterministic grounding or human-approval
boundaries established in V4 and V5.

### V6.1 Agent REST Contracts

Strict Pydantic contracts define:

- Investigation-start requests
- Human approval and rejection requests
- Active, waiting, completed, failed, and abstained run responses
- Nested diagnosis, proposal, interrupt, and decision payloads
- Run and thread identity validation
- Terminal and active lifecycle timestamp rules

Unknown fields are rejected. Streamlit and FastAPI share the same contracts rather
than maintaining separate untyped payload formats.

### V6.2 Persisted Agent Workflow Services

Application services own the complete REST-facing workflow:

- Start and persist a new agent investigation
- Return the latest persisted run and checkpoint state
- Apply a human approval or rejection
- Resume the correct LangGraph thread
- Preserve run, thread, work-order, approval, version, and scope identity
- Return controlled not-found, conflict, persistence, and execution errors

The service layer remains independent of HTTP and can be tested using fake models,
temporary SQLite databases, and local checkpoints.

### V6.3 FastAPI Routes and Production Runtime

The application exposes:

- `POST /agent/investigations`
- `GET /agent/runs/{run_id}`
- `POST /agent/runs/{run_id}/approval`

The production runtime factory composes the database session factory, deterministic
tools, hosted-model provider, LangGraph, and SQLite checkpointer. Runtime creation
is lazy and lock-protected, so `GET /health` and application import do not make
hosted-model calls.

FastAPI lifespan cleanup closes the checkpoint connection safely. Strict
checkpoint deserialization uses an explicit allowlist containing only trusted
application state types. Persisted diagnosis, evidence, grounding, proposal, and
approval state has been verified across process restart.

### V6.4 Persisted Runtime Observability

Every investigation persists an `agent_runs` record. Instrumented graph nodes add
ordered `agent_steps`, while real tool execution adds linked `tool_calls`.

Recorded telemetry includes:

- Provider and model name
- Run lifecycle status and duration
- Ordered graph-node type, status, latency, and controlled failure details
- Tool name, actual arguments, result or error, and latency
- Read-only or state-changing classification
- Approval linkage for non-blocked state-changing calls
- Model-call count
- Provider-reported prompt, completion, and total tokens

Model usage is collected from actual `AIMessage.usage_metadata`. Estimated cost is
left at zero because deployment-specific pricing is not available from the model
response and is not fabricated.

### V6.5 Streamlit Operator Dashboard

The Streamlit interface provides:

- Configurable FastAPI base URL and request timeout
- Typed investigation form with asset and iteration controls
- Revalidated JSON-compatible session state
- Persisted run refresh
- Run, thread, and lifecycle status
- Grounded diagnosis, confidence, likely causes, and safety notes
- Expandable evidence summaries and citations
- Recommended-action and proposed-work-order details
- Explicit human approve and reject controls
- Required operator identity and decision reason
- Stale or conflicting approval guidance
- Final human-decision display

The dashboard uses the typed HTTPX2 client and translates connection, HTTP,
invalid-JSON, and contract failures into controlled operator messages. It does not
receive Azure credentials and does not call the hosted model directly.

Automated UI tests use fake clients and Streamlit's application-testing interface.
Normal test execution does not make billable hosted-model calls.

## V7 Evaluation and Reliability

### V7.1 Evaluation Contracts and Core Dataset

V7.1 defines the machine-readable specification used by later evaluation runners
and scorers.

Strict Pydantic contracts define:

- Versioned evaluation datasets and scenario identities
- Normal, degraded, contradictory, insufficient-evidence, and adversarial taxonomy
- Expected tool names, arguments, and call ranges
- Required and forbidden tools
- Expected terminal status, diagnosis outcome, and grounding decision
- Required evidence sources and diagnosis citations
- Claim locations, required concepts, and supporting citations
- Explicit citation exceptions for missing-evidence limitations
- Proposal and approval-pause expectations
- Global safety invariants

The versioned `v7.core` JSON dataset contains 15 scenarios, with three scenarios
for each required taxonomy category. It includes grounded and abstained outcomes,
proposal and no-proposal paths, partial and unavailable evidence, contradictory
user claims, prompt injection, approval bypass attempts, and prohibited direct
machinery-control requests.

The dataset loader rejects empty paths, missing files, malformed JSON, non-object
roots, unknown fields, duplicate scenario identities, duplicate required
categories, and missing declared taxonomy categories.

V7.1 scenarios are evaluation specifications; they are not fabricated evaluation
scores and do not execute the agent by themselves.

### V7.2 Deterministic Scorers

V7.2 provides pure deterministic scoring functions for:

- Terminal run status, investigation outcome, and grounding decision
- Required evidence-source coverage
- Exact citation validity and required-citation completeness
- Required and forbidden tool selection
- Exact tool-argument correctness
- Required diagnosis concepts at declared claim locations
- Expected citation support for citation-required claims
- Forbidden claim concepts
- Deterministic work-order proposal eligibility
- Human-approval pause integrity
- Bounded graph trajectory behavior
- The read-only physical-execution boundary

Every metric produces a strict machine-readable binary result containing its
metric name, pass or fail status, score, summary, expected value, actual value,
and failure details. All current V7.2 metrics pass only with a score of `1.0`;
binary failures receive `0.0` and explicit diagnostic details.

Claim support is currently a deterministic external proxy: it verifies that each
citation-required expected claim has its declared citation in the diagnosis
evidence list. The production diagnosis schema does not yet represent a direct
claim-to-citation semantic link, so V7.2 does not fabricate semantic-entailment
scores.

The scorers consume typed application schemas and observability records but do
not execute the agent, access the database, or invoke a hosted model.
Deterministic scenario execution is supplied by V7.3.

The verified V7.2 checkpoint contains 378 automated tests. Normal automated tests
make zero billable hosted-model calls.

### V7.3 Deterministic Scenario Runner and Regression Report

V7.3 executes the complete 15-scenario core dataset through the real LangGraph
workflow without making billable hosted-model calls. Each scenario receives a
fresh isolated working environment containing a seeded SQLite database, persistent
Chroma collection, LangGraph checkpoint database, and scenario-scoped fixture
mutations.

Deterministic scripted models preserve the real model-tool-model transitions while
controlling tool calls and structured diagnoses. The mutation layer supports
asset-scoped missing, empty, limited, contradictory, and adversarial evidence
conditions without modifying the source dataset.

The runner collects real workflow state and persisted observability records before
applying every V7.2 metric. It returns typed scenario and dataset results with
distinct `passed`, `failed`, and `error` outcomes.

The command-line runner writes an atomic machine-readable JSON report:

```bash
python -m app.evaluation.cli
```

The verified `v7.core` regression run completed all 15 scenarios with 15 passed,
zero failed, and zero execution errors. The verified V7.3 checkpoint contains 487
automated tests. Normal evaluation and automated-test execution make zero billable
hosted-model calls.

### V7.4 Continuous Integration Quality Gate

V7.4 adds a read-only GitHub Actions workflow for every push and pull request
targeting `main`. The workflow creates a clean Python 3.11 Ubuntu environment,
installs the pinned development dependencies, checks dependency compatibility,
verifies Ruff formatting and linting, and executes the complete automated test
suite.

Workflow concurrency cancels superseded runs, while a 20-minute timeout prevents
stalled jobs from running indefinitely. The workflow receives no Azure credentials
and the deterministic evaluation suite makes no billable hosted-model calls.

The first remote run exposed an operating-system-dependent import classification.
The project now declares `app` as a Ruff first-party package, producing consistent
import ordering on Windows and Linux. The corrected workflow completed
successfully on GitHub Actions with all 487 automated tests passing.

### V8.1 API Container Foundation

V8.1 introduces a production-oriented Docker image for the Maintenance Copilot
API.

The image uses Python 3.11 slim and installs CPU-only PyTorch dependencies to
avoid unnecessary GPU runtime components. The application runs as the non-root
`maintenance` user and exposes the FastAPI service on port 8000.

Runtime data is separated from the application source under `/app/runtime`, and
the container includes a health check against the existing `/health` endpoint.
The Docker build context excludes secrets, generated databases, Chroma runtime
data, test artifacts, and other local development files.

Automated container-contract tests verify the pinned runtime, CPU-only dependency
policy, non-root execution, persistent runtime paths, health contract, and
Docker build-context exclusions.


### V8.2 Container Startup and Local Orchestration

V8.2 adds an idempotent container startup layer and Docker Compose orchestration
for the API and Streamlit operator dashboard.

When `INITIALIZE_APPLICATION_DATA=true`, the container startup process applies
Alembic migrations, seeds the deterministic industrial dataset, and indexes the
engineering-document corpus before launching the requested application command.
Repeated startup preserves existing seeded application data.

Docker Compose runs the API and dashboard from the same application image. The
API receives hosted-model credentials through its environment while the dashboard
communicates with the API through the internal Compose network without receiving
Azure credentials.

A named runtime volume preserves SQLite application data, LangGraph checkpoints,
Chroma data, and model cache across normal local container restarts.

The verified V8.2 local container journey successfully executed a grounded P-101
investigation through the Streamlit dashboard, API, LangGraph workflow,
Azure-hosted model, SQLite tools, and engineering-document retrieval layer.


### V8.3 Container Continuous Integration Gate

V8.3 extends the GitHub Actions workflow with a Docker container quality gate.

The container job runs only after the Python quality job succeeds. It builds the
production image on Ubuntu, verifies that the configured runtime user is
`maintenance`, starts the API container without hosted-model credentials, and
waits for a successful response from `/health`.

Container logs are collected and the smoke-test container is removed even when
the job fails.

This gate proves that every accepted commit can build and start the production
container independently of the developer workstation and without making billable
hosted-model calls.


### V8.4 Azure Application Deployment and Hosted Validation

V8.4 deploys the Maintenance Copilot infrastructure and application to Azure
using Bicep, Azure Container Registry, and Azure Container Apps.

The temporary Azure foundation provisions the Container Apps environment,
Azure Container Registry, Log Analytics integration, managed identity for image
pulls, and runtime-storage resources. Infrastructure templates are validated by
automated contract tests and by the GitHub Actions quality gate.

The API and Streamlit dashboard are deployed as separate Container Apps using the
same application image. Azure OpenAI credentials are supplied to the API through
Container App secrets, while the dashboard communicates with the API without
receiving hosted-model credentials.

Hosted troubleshooting identified that SQLite, LangGraph checkpoint storage, and
Chroma require replica-local filesystem semantics that are not provided by the
Azure Files SMB mount used by the temporary deployment. The hosted API therefore
uses:

- `/tmp/maintenance_copilot.db`
- `/tmp/langgraph_checkpoints.sqlite`
- `/tmp/chroma`

These paths allow the application to run correctly within the active replica but
are not claimed to survive replica replacement.

The final hosted image `f9293d6` was deployed successfully to Azure Container Apps.
The resulting API revision became healthy and provisioned.

A real hosted P-101 investigation then validated the complete human-in-the-loop
workflow:

- grounded evidence was collected through the deployed application;
- the agent produced a grounded diagnosis;
- a controlled inspection recommendation was correctly classified as requiring
  a work-order proposal;
- the application created a pending work order and approval request;
- the Streamlit dashboard rendered the human approval controls;
- a human operator approved the work order;
- LangGraph resumed from the approval interrupt;
- the work order transitioned to `approved`;
- the investigation reached `completed`;
- refreshing the dashboard retrieved the same persisted application state.

The approval remained strictly application-level. No physical maintenance
execution, machinery control, PLC modification, or interlock bypass was performed
or recorded.

The verified V8.4 checkpoint contains 529 automated tests.

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
- HTTPX2
- Streamlit
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
|   |-- model_observability.py
|   |-- nodes.py
|   |-- observability.py
|   |-- policy.py
|   |-- proposal.py
|   |-- runtime.py
|   |-- state.py
|   |-- synthesis.py
|   |-- tool_node.py
|   `-- tool_observability.py
|-- api/
|   |-- dependencies.py
|   `-- routes/
|       |-- agent.py
|       `-- health.py
|-- core/
|   |-- config.py
|   `-- logging.py
|-- evaluation/
|   |-- cli.py
|   |-- environment.py
|   |-- execution.py
|   |-- fixture_registry.py
|   |-- fixtures.py
|   |-- mutations.py
|   |-- reporting.py
|   |-- runner.py
|   |-- scoring.py
|   `-- scripted_models.py
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
|   |-- agent_api.py
|   |-- diagnosis.py
|   |-- evidence.py
|   |-- hitl.py
|   |-- investigation.py
|   |-- observability.py
|   `-- tool-specific schemas
|-- services/
|   |-- agent_workflows.py
|   |-- approvals.py
|   |-- exceptions.py
|   |-- observability.py
|   `-- work_orders.py
|-- tools/
|-- ui/
|   |-- api_client.py
|   |-- approval_panel.py
|   |-- dashboard.py
|   |-- operator_actions.py
|   `-- run_views.py
`-- main.py

data/
|-- engineering_docs/
`-- .gitkeep

migrations/
tests/
streamlit_app.py
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

Available application endpoints:

- `POST /agent/investigations`
- `GET /agent/runs/{run_id}`
- `POST /agent/runs/{run_id}/approval`

The Swagger UI exposes the typed request and response contracts. Starting the API
or calling `GET /health` does not invoke the hosted model. A hosted-model call
occurs only when an investigation request reaches the agent workflow.

## Run the Operator Dashboard

Start FastAPI in the first terminal:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
## Docker and Local Orchestration

V8.1 provides a production-oriented API image based on Python 3.11 slim with
CPU-only PyTorch dependencies. The container runs as the non-root `maintenance`
user, exposes port 8000, writes application data only under `/app/runtime`, and
uses the API health endpoint for its container health check.

V8.2 adds an idempotent container startup process. When
`INITIALIZE_APPLICATION_DATA=true`, startup applies Alembic migrations, seeds the
SQLite database, and indexes the engineering-document corpus before launching the
requested application process. Repeated startup preserves existing seeded data.

Docker Compose runs the API and Streamlit dashboard from the same image. The API
receives application credentials through `.env`, while the dashboard communicates
with the API over the internal Compose network without receiving Azure credentials.
A named volume preserves the SQLite database, Chroma collection, model cache, and
LangGraph checkpoint data across normal container restarts.

Build and start the complete local stack:

```bash
docker compose up --build --detach
```

Check container health:

```bash
docker compose ps
docker compose logs --tail 50 api
```

Open the services:

- API health: `http://127.0.0.1:8000/health`
- Streamlit dashboard: `http://127.0.0.1:8501`

Stop the stack while preserving runtime data:

```bash
docker compose down
```

Running `docker compose down --volumes` also deletes the named runtime volume and
its persisted local application data.

The V8.2 hosted smoke test successfully executed a real grounded P-101
investigation through the dashboard, Compose network, API, LangGraph workflow,
Azure-hosted model, SQLite tools, and engineering-document retrieval layer.
No physical maintenance execution or machinery-control action was performed.

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

Run the complete deterministic evaluation dataset:

```bash
python -m app.evaluation.cli
```

The default machine-readable report is written to
`reports/evaluation/v7_core_result.json`. Use `--overwrite` only when intentionally
replacing an existing report.

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
- V6 - Application and Observability: complete
- V7 - Evaluation and Reliability: complete
- V8 - Docker and Azure: complete

The MVP is complete.
