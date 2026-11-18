# n8n workflow example

Import `maintenance-workflow.json` into n8n as a new workflow.

The example is inactive and its Schedule Trigger is disabled.
Credentials and instance-specific references have been removed.

## Configure before running

1. Select your Telegram credentials in Telegram Trigger and both
   Telegram message nodes.
2. Replace the chat ID placeholder `0` in the `If` node's authorization
   expression and both Telegram message nodes with your Telegram chat ID.
3. Create a data table named `temperature_alert_state` with:
   - `asset_code`: string
   - `is_above_threshold`: boolean
4. Add a row with `asset_code` set to `P-101` and
   `is_above_threshold` set to `false`.
5. Select that table in `Get row(s)`, `Update row(s)`, and `Update row(s)1`,
   replacing `YOUR_DATA_TABLE_ID`.
6. Replace `https://example.com/dashboard` in the alert's inline keyboard
   with a dashboard URL reachable from your phone.
7. Check both HTTP Request URLs. The default API address is
   `http://127.0.0.1:8000`, suitable when n8n runs directly on the API host.
   Containerized n8n requires an address reachable from its container.
8. Configure a public HTTPS webhook address for the Telegram Trigger.

## Manual verification

With the API running and the P-101 temperature above 75 degrees Celsius:

1. Keep Schedule Trigger disabled.
2. Execute the manual trigger with the stored alert state set to false.
3. Confirm that one alert arrives and the stored state becomes true.
4. Execute again and confirm that the repeated alert is suppressed.

The below-threshold branch resets the stored state to false.

Send `/lastservice P-101` from the authorized Telegram chat to check
maintenance-history lookup.

Enable Schedule Trigger and publish only after configuration and testing.

## Limitations

The example uses historical demonstration readings and does not check
reading freshness. Alert suppression depends on the existing data-table
row and does not guarantee exactly-once delivery under concurrent runs.

See [integration documentation](../../docs/integrations.md) and the
[demo guide](../../docs/demo-guide.md).