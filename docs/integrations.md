# Telegram, n8n, and MCP Integrations

## Overview

The project exposes maintenance information through three interfaces:

| Interface | Purpose |
|---|---|
| Streamlit dashboard | Investigation, evidence review, and human decisions |
| Telegram through n8n | Maintenance-history lookup and temperature notifications |
| MCP server | Structured maintenance lookup for MCP clients |

Telegram and MCP call the FastAPI lookup endpoints. They do not run the complete
investigation agent or invoke Azure OpenAI for these lookups.

The demonstrated setup runs n8n and the MCP server on the laptop, while FastAPI,
Streamlit, and PostgreSQL run in Docker.

## Integration endpoints

| Endpoint | Purpose |
|---|---|
| `GET /assets/{asset_code}/last-service` | Return the latest maintenance record |
| `GET /assets/{asset_code}/latest-temperature` | Return the latest temperature reading |

The latest-temperature endpoint returns the reading ID, value, unit, and timestamp.
It returns HTTP 404 when no matching reading exists and HTTP 409 when the latest
reading is not good quality.

These endpoints expose application data. They do not execute maintenance actions.

## Telegram maintenance lookup

Example command:

```text
/lastservice P-101
```

The n8n workflow:

1. Receives the Telegram message.
2. Checks the configured chat restriction and command format.
3. Extracts the asset code.
4. Calls the FastAPI last-service endpoint.
5. Formats and sends the maintenance record to Telegram.

The verified P-101 response returned maintenance record ID `3`, an inspection
performed on 5 November 2026.

A maintenance-record ID belongs to the `maintenance_records` table. It is separate
from a work-order ID or approval ID, even when their numeric values happen to match.

## Temperature notification workflow

The demonstration checks P-101 temperature every minute through a Schedule Trigger.
A Manual Trigger supports controlled testing of the same path.

The threshold is:

```text
temperature > 75 degrees Celsius
```

This is a demonstration threshold, not an engineering alarm limit or equipment
shutdown setting.

### Alert state

The n8n Data Table `temperature_alert_state` contains:

| Column | Type | Purpose |
|---|---|---|
| `asset_code` | String | Asset being monitored |
| `is_above_threshold` | Boolean | Whether an alert has already been recorded for the current high state |

Create one row for `P-101` with `is_above_threshold` initially set to false.

The workflow uses Get Row(s) to retrieve the asset row, followed by an If node
that checks the Boolean value. It does not filter the Data Table using a textual
`"false"` value.

### Decision behavior

| Temperature | Stored state | Behavior |
|---|---|---|
| Above 75 | false | Send alert, then set state to true |
| Above 75 | true | Suppress repeated alert |
| At or below 75 | Either | Set state to false |

The high-temperature path is:

1. HTTP Request retrieves the latest temperature.
2. If checks whether the value exceeds 75.
3. Get Row(s) retrieves the asset's alert state.
4. A second If checks whether `is_above_threshold` is false.
5. Telegram sends the alert.
6. Update Row(s) sets the stored state to true.

The normal-temperature branch updates the stored state to false, allowing a future
high-temperature event to send another alert.

The asset state row must exist. The current workflow does not automatically create
missing rows.

### Alert message and dashboard button

The alert includes:

- Asset code
- Temperature
- Demonstration threshold
- Reading timestamp
- An inline keyboard button that opens the dashboard

Read the temperature fields from the HTTP Request node explicitly. The Data Table
and Telegram nodes can replace the current item's fields, so `$json.value` is not
reliable at every downstream node.

The dashboard URL must be reachable from the device opening the button.
`localhost` on a phone refers to the phone, not the laptop.

Phone access was demonstrated with the laptop connected to the phone's hotspot.
The button used the laptop's hotspot IP and port 8501. This is a local network
demonstration, not a publicly hosted dashboard URL.

## n8n and ngrok setup

The demonstrated n8n installation runs natively on the laptop on port 5678.

Start the tunnel in one terminal:

```bat
ngrok http 5678
```

In another terminal, replace the example tunnel URL with the current HTTPS
forwarding URL:

```bat
set "NODE_OPTIONS=--dns-result-order=ipv4first"
set "N8N_WEBHOOK_URL=https://YOUR-TUNNEL-DOMAIN/"
set "N8N_PROXY_HOPS=1"
npx n8n
```

The IPv4-first setting resolved the Telegram connectivity problem observed in the
demonstrated environment.

Open n8n, configure Telegram credentials, and publish the workflow. Production
Telegram messages use the published webhook workflow; manual workflow execution
is not required for every incoming message.

The local ngrok inspection interface is available at:

```text
http://127.0.0.1:4040
```

In the demonstrated topology, n8n HTTP Request nodes call:

```text
http://127.0.0.1:8000
```

If n8n is moved into Docker, its network address configuration must be changed.
Container loopback does not refer to the laptop's FastAPI port.

## MCP maintenance lookup

The Python MCP server is implemented in:

```text
app/mcp_server.py
```

It exposes:

```text
get_last_service(asset_code: str)
```

The tool validates and normalizes the asset code, calls the FastAPI last-service
endpoint, and returns structured maintenance data.

The request follows:

MCP client → MCP server → FastAPI → PostgreSQL.

The MCP tool does not directly query pgvector or run a diagnosis.

### MCP Inspector

Activate the project environment and launch Inspector from the repository root:

```bat
conda activate MaintenanceCopilot
npx @modelcontextprotocol/inspector
```

Configure the server:

| Setting | Value |
|---|---|
| Transport | STDIO |
| Command | `python` |
| Arguments | `-m app.mcp_server` |
| Working directory | Project repository root |

If the Inspector UI has separate argument fields, enter `-m` and
`app.mcp_server` as separate arguments.

Connect the server, select Tools, choose `get_last_service`, enter `P-101`, and
execute the tool.

The argument form is generated from the tool's schema. Successful execution
returns the structured API response.

FastAPI must already be running. The MCP server provides the protocol/tool layer;
it does not start the API.

## Verification performed

| Check | Observed result |
|---|---|
| Telegram maintenance lookup | Bot returned P-101 maintenance history |
| First scheduled high-temperature check | Alert sent |
| Subsequent high-temperature check | Alert suppressed |
| Manual reset and alert test | Alert sent after state reset |
| Dashboard inline button | Opened the dashboard on the phone |
| MCP Inspector tool call | Returned maintenance record ID `3` |
| Lookup after PostgreSQL migration | Telegram and MCP both succeeded against the Docker API |

The alert reset path was tested using a temporary threshold change and state
reset. This is not claimed as a live sensor normal-high-normal-high transition test.

## Limitations

- The sensor readings are synthetic historical demo data.
- The current notification workflow does not reject stale timestamps.
- Alert state remains in n8n's Data Table, separate from PostgreSQL application data.
- The demonstrated configuration monitors one preconfigured asset.
- The read-send-update sequence is not an atomic exactly-once delivery guarantee.
  Overlapping runs or a failure after sending but before updating state can cause
  duplicate alerts.
- The dashboard button depends on the configured network address remaining reachable.
- Published schedule execution requires n8n to remain running and the trigger enabled.
- The ngrok tunnel must remain available for Telegram webhook delivery.
- A successful maintenance lookup does not prove a physical service was performed.

## Sharing workflow exports

Before committing an exported workflow:

1. Remove credential references and account-specific identifiers.
2. Replace chat IDs, tunnel URLs, dashboard addresses, and local paths with placeholders.
3. Remove pinned execution data.
4. Check node parameters and headers for tokens or other credentials.
5. Document the Telegram credentials and Data Table that the importer must create.

An exported workflow does not include the live Data Table contents or provide
working Telegram credentials.

Human approval remains in the Copilot application's controlled workflow.
Telegram notifications and the MCP lookup tool do not bypass that approval.