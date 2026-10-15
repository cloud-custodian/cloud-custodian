# Cost Management Scheduled Action Recording

`cost-management-scheduled-action.json` deploys `Microsoft.CostManagement/scheduledActions`
(kind `InsightAlert`), which is a subscription-scoped resource. It deviates from the
`provision.sh`/`cleanup.sh` convention documented in `readme.md`, which deploys every
template with `az deployment group create` against a resource group named
`test_<filename>`. This resource can't be deployed that way: giving it a `scope`
override pointing at the subscription inside a resource-group deployment doesn't switch
scope - ARM instead concatenates the scope string as a literal path segment under the
resource group, producing a malformed resource ID and an `InvalidTemplate` error.

## Provisioning

Deploy directly at subscription scope instead of using `provision.sh`. Commands below
assume you're running from the repo root:

```bash
az deployment sub create \
    --location "South Central US" \
    --name cost-management-scheduled-action \
    --template-file tools/c7n_azure/tests_azure/templates/cost-management-scheduled-action.json
```

## Cleanup

`az resource delete` resolves to the resource provider's latest reported API version by
default, but the `scheduledactions.costmgmt.azure.com` endpoint this resource lives on
only supports the fixed version deployed above - pin it explicitly:

```bash
az resource delete \
    --api-version 2023-11-01 \
    --ids "$(az deployment sub show \
        --name cost-management-scheduled-action \
        --query 'properties.outputResources[0].id' -o tsv)"
```

`az deployment sub show` keeps returning the deployment's historical record (including
`outputResources`) after this - that's expected and isn't evidence the delete failed;
the deployment history is independent of whether the resource still exists. Verify the
resource is actually gone by querying it directly (expect `ResourceNotFound`):

```bash
az resource show --api-version 2023-11-01 \
    --ids "/subscriptions/<subscription-id>/providers/Microsoft.CostManagement/scheduledActions/cctestscheduledaction"
```

## Recording

The repo's `test.env` (auto-loaded by the `pytest-env` plugin via `env_files` in the
root `pyproject.toml`) sets `AZURE_ACCESS_TOKEN=fake_token` for every test run.
`azure_common.py` forces VCR's `record_mode` to `'none'` whenever that variable is set,
which raises `CannotOverwriteExistingCassetteException` on any unmatched request even
when no cassette file exists yet. Disable the plugin with `-p no:env` so your real `az
login` credentials are used instead, and VCR's default `record_mode` (`'once'`) can
write a fresh cassette against the live resource:

```bash
uv run --project tools/c7n_azure pytest -p no:env \
    tools/c7n_azure/tests_azure/tests_resources/test_cost_management_scheduled_action.py::CostManagementScheduledActionTest::test_resource \
    -q
```

### Recording `test_z_enable_disabled_alert`

This test needs the scheduled action deployed *disabled*, since it exercises the
`update` action's enable path. Deploy with the `status` parameter overridden:

```bash
az deployment sub create \
    --location "South Central US" \
    --name cost-management-scheduled-action \
    --template-file tools/c7n_azure/tests_azure/templates/cost-management-scheduled-action.json \
    --parameters status=Disabled
```

Then record against it the same way, with real `az login` credentials:

```bash
uv run --project tools/c7n_azure pytest -p no:env \
    tools/c7n_azure/tests_azure/tests_resources/test_cost_management_scheduled_action.py::CostManagementScheduledActionTest::test_z_enable_disabled_alert \
    -q
```

Clean up afterwards the same way described above under Cleanup.
