# PostgreSQL and pgvector

## Overview

The current integration replaces SQLite application storage with PostgreSQL and
Chroma document retrieval with pgvector.

PostgreSQL stores assets, maintenance records, sensor readings, work orders,
approvals, agent observability, document chunks, metadata, and embeddings.

LangGraph checkpoints remain in a separate SQLite database. PostgreSQL migration
does not migrate or replace the checkpoint store.

Implementation checkpoint: `4974d98`.

## Storage architecture

| Data | Current storage |
|---|---|
| Assets and maintenance history | PostgreSQL |
| Sensor readings | PostgreSQL |
| Work orders and human decisions | PostgreSQL |
| Agent runs, steps, and tool calls | PostgreSQL |
| Engineering documents and embeddings | PostgreSQL with pgvector |
| LangGraph checkpoints | SQLite |
| Embedding model cache | Local filesystem or Docker runtime volume |
| Telegram alert state | n8n Data Table |

The application uses SQLAlchemy and Psycopg to communicate with PostgreSQL.
`SQLVectorStore` provides document indexing and retrieval.

PostgreSQL performs vector-distance queries through pgvector. Isolated SQLite
tests and deterministic evaluation use JSON vector storage and Python distance
calculation through the same storage interface.

## Versions verified locally

| Component | Version |
|---|---|
| PostgreSQL image family | PostgreSQL 17 |
| pgvector extension | 0.8.7 |
| Docker image | `pgvector/pgvector:0.8.7-pg17-trixie` |
| Python pgvector package | 0.5.1 |
| Psycopg and binary package | 3.3.9 |
| Alembic | 1.19.2 |

The image tag pins the pgvector release and PostgreSQL major version; it does not
pin an immutable image digest.

## Database schema

Application tables:

- `assets`
- `maintenance_records`
- `sensor_readings`
- `work_orders`
- `approvals`
- `agent_runs`
- `agent_steps`
- `tool_calls`

RAG tables:

- `rag_collections`
- `rag_chunks`

Alembic tracks the active schema in `alembic_version`.

`rag_collections` records the collection name, embedding dimension, and embedding
model identifier. `rag_chunks` stores the chunk ID, content, metadata, dimension,
and embedding.

A composite foreign key connects each chunk to its collection and dimension.
PostgreSQL also checks that the stored vector dimension matches the declared
chunk dimension.

Migration revisions:

| Revision | Purpose |
|---|---|
| `0e66bfb68f1d` | Industrial application schema |
| `6f4506da2226` | Engineering-document vector storage |

## Connection configuration

Copy `.env.example` to `.env` when setting up a fresh checkout. Configure the
database password before initializing PostgreSQL.

For the current local Compose configuration, use a password containing letters
and numbers. Keep the password in `POSTGRES_PASSWORD` and the password portion
of the local `DATABASE_URL` consistent.

| Caller | Database hostname |
|---|---|
| Python running on the laptop | `127.0.0.1` |
| API running inside Compose | `postgres` |

The main Compose file supplies the container database URL. The `.env` database URL
is used by local Python commands.

Changing `POSTGRES_PASSWORD` after the database volume has been initialized does
not change the existing PostgreSQL role password.

The PostgreSQL port is published on laptop loopback only. Phone access to the
dashboard does not require exposing PostgreSQL.

Never commit populated credentials or include database URLs with passwords in
screenshots.

## Docker services and persistence

The main `compose.yaml` runs PostgreSQL, FastAPI, and Streamlit.

| Volume | Contents |
|---|---|
| `maintenance-postgres-data` | PostgreSQL application and vector data |
| `maintenance-runtime` | Local container checkpoints and model cache |

Both Compose files use the same project name and PostgreSQL volume name.
`compose.postgres.yaml` supports running only the database for local Python
development. Use the main Compose file for the complete application stack.

Normal container replacement preserves named-volume data. Removing the volumes
deletes the corresponding persisted data.

## SQLite data migration

`migrate_sqlite_to_postgres.py` transfers the original application records from
`data/maintenance_copilot.db` to the PostgreSQL URL configured in `.env`.

The script:

1. Opens the SQLite source in read-only mode.
2. Checks that the source contains the expected application tables.
3. Refuses to overwrite non-empty destination application tables.
4. Copies records in dependency order while preserving IDs.
5. Restores asset parent relationships.
6. Treats naive source timestamps as UTC and normalizes timestamps to UTC.
7. Compares every copied row before committing.
8. Advances PostgreSQL-generated ID sequences beyond imported IDs.

The UTC interpretation follows the application's UTC timestamp and seed
conventions. It is not a general timezone-conversion rule for arbitrary SQLite
databases.

The verified migration copied:

| Table | Records |
|---|---:|
| `assets` | 4 |
| `maintenance_records` | 7 |
| `sensor_readings` | 2,520 |
| `work_orders` | 2 |
| `approvals` | 2 |
| `agent_runs` | 2 |
| `agent_steps` | 12 |
| `tool_calls` | 2 |
| **Total** | **2,551** |

These counts describe the migration checkpoint. Later investigations and human
decisions add application records.

### Reproducing migration

Migration is an alternative to seeding a fresh database. Do not run the full
application initializer first: it seeds destination tables, which causes the
migration script to refuse the copy.

With the original SQLite source available, local dependencies installed, `.env`
configured, and an empty PostgreSQL destination, run:

```bat
docker compose -f compose.postgres.yaml up -d --wait
python -m alembic upgrade head
python migrate_sqlite_to_postgres.py
python -m app.rag.indexer
```

The source SQLite file remains unchanged. The migration script is intended for the
original application schema and is not a general-purpose migration utility.

## Engineering-document indexing

The corpus contains three synthetic engineering documents, split into nine stable
section-level chunks.

The embedding model remains:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Production embeddings contain 384 normalized dimensions.

Indexing stores the original chunk IDs, content, and metadata:

- Document ID
- Title
- Section
- Source path
- Applicable assets

The current process rebuilds embeddings from the source documents. It does not
copy an existing Chroma index or claim bit-for-bit embedding equality with a
previous index.

Index locally:

```bat
python -m app.rag.indexer
```

Expected output includes:

```text
Collection: engineering_docs
Source documents: 3
Indexed chunks: 9
Embedding dimension: 384
Stored chunks: 9
```

Indexing replaces only the named collection in one transaction. Repeated indexing
does not duplicate chunks, and chunks removed from the source corpus are removed
from that collection.

## Retrieval behavior

The search tool:

1. Checks that the collection contains documents.
2. Embeds the query.
3. Retrieves a bounded candidate set using vector distance.
4. Applies the existing asset-applicability filter.
5. Applies minimum relevance filtering.
6. Returns up to the requested number of results with citations.

PostgreSQL's L2 distance is squared before returning it through the application
interface. The SQLite path calculates squared L2 directly.

The relevance calculation is:

```text
relevance_score = 1 / (1 + max(distance, 0))
```

This score is a retrieval heuristic, not a probability that a diagnosis is correct.

Retrieval uses exact distance ordering. No HNSW or IVFFlat index is configured for
the nine-chunk demo corpus. Large-corpus performance has not been benchmarked.

Asset filtering occurs after candidate retrieval. A restrictive filter can return
fewer than `top_k` results even when additional applicable chunks exist outside
the candidate set.

The collection stores an embedding model identifier, but search currently checks
vector dimension rather than enforcing model identity. Use the same model for
indexing and querying; reindex when changing it.

## Automated verification

The verified local suite completed with:

```text
536 passed
```

This included five integration tests against real PostgreSQL and pgvector:

- Retrieval ordering, metadata, content, and squared distance.
- Repeated indexing and removal of obsolete chunks.
- Transaction rollback after a database insert failure.
- Rejection of incorrect query dimensions.
- Missing and cleared collection behavior.

The integration tests use a separate `maintenance_copilot_test` database.
They create uniquely named test collections and clean up those collections.

Create the test database once:

```bat
docker compose exec postgres psql -U maintenance -d postgres -c "CREATE DATABASE maintenance_copilot_test;"
```

If it already exists, reuse it.

Run the full suite from Windows Anaconda Prompt:

```bat
set "RUN_POSTGRES_TESTS=1"
python -m pytest -q
set "RUN_POSTGRES_TESTS="
```

With the flag unset, the five PostgreSQL integration tests are skipped. The current
GitHub Actions workflow does not provision their PostgreSQL service or enable the
flag. The 536-pass result is local validation, not a claimed remote CI result.

Additional checks:

```bat
python -m ruff format --check .
python -m ruff check .
python -m pip check
python -m alembic check
```

Alembic 1.19.2 is used with named CHECK-constraint comparison explicitly enabled.
Version 1.19.1 produced false enum-constraint removal reports during migration
verification.

## Manual validation

The following were verified with the local Docker stack:

- All three services became healthy.
- Latest-temperature and last-service endpoints returned HTTP 200.
- P-101 retained temperature reading ID `837` with value `77.124 degC`.
- P-101 retained latest maintenance record ID `3`.
- Real pgvector retrieval returned engineering excerpts and citations.
- A live Azure OpenAI investigation collected all four evidence categories.
- The dashboard displayed a diagnosis with 13 evidence references.
- A human approval persisted in PostgreSQL.
- Telegram and MCP continued retrieving maintenance history through the Docker API.

These checks establish the demonstrated integration behavior. They are not
large-scale load tests or proof of diagnosis accuracy on real machinery.

## Startup limitation after application data grows

The current seed initializer validates exact demo record counts when assets already
exist. New work orders or approvals can therefore cause initialization to reject
an otherwise valid database on a subsequent API startup.

For an already initialized database containing investigation results, set the API's
`INITIALIZE_APPLICATION_DATA` setting to `"false"` in Compose before recreating
the API container. Apply migrations and indexing explicitly when required.

Do not delete valid records or reset the PostgreSQL volume to satisfy seed counts.
A seed-initialization improvement is outstanding.

## Deployment scope and known limits

- PostgreSQL and pgvector were verified locally and through Docker.
- Azure templates now accept the database URL through a secret parameter.
- This upgraded stack has not been redeployed with an Azure-accessible PostgreSQL
  service.
- LangGraph checkpoints remain SQLite. Local Compose persists them in a volume;
  the Azure template keeps them replica-local.
- The proposed-work-order panel can retain a stale pending status after approval.
  The decision panel and PostgreSQL records showed the approved state.
- An old dashboard banner still refers to approval controls as a future feature.
- Concurrent first-time indexing of the same new collection has not been verified.
- Synthetic sensor data and documents are demonstration inputs.

Human approval changes application records only. It does not perform physical
maintenance or control machinery.