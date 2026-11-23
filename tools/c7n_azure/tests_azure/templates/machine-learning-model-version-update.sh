#!/bin/bash
# Provision the ARM template first, then run this script with its uniqueId.
set -euo pipefail

template_directory="$(cd "$(dirname "$0")" && pwd)"
unique_id="$1"
resource_group="test_machine-learning-model-version-update"
workspace="cctest-ml-update-${unique_id}"
workspace_id="$(az resource show -g "$resource_group" -n "$workspace" \
    --resource-type Microsoft.MachineLearningServices/workspaces --query id -o tsv)"
datastore="$(az rest --method get \
    --url "https://management.azure.com${workspace_id}/datastores/workspaceblobstore?api-version=2023-04-01")"
account="$(printf '%s' "$datastore" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["properties"]["accountName"])')"
container="$(printf '%s' "$datastore" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["properties"]["containerName"])')"
export AZURE_STORAGE_ACCOUNT="$account"
AZURE_STORAGE_KEY="$(az storage account keys list -g "$resource_group" \
    -n "$account" --query '[0].value' -o tsv)"
export AZURE_STORAGE_KEY

artifact="$(mktemp)"
trap 'rm -f "$artifact"' EXIT
printf 'Cloud Custodian test model artifact\n' > "$artifact"
az storage blob upload --container-name "$container" \
    --name models/original/model.txt --file "$artifact" \
    --overwrite --output none

az deployment group create -g "$resource_group" -n update-model-registration \
    --template-file "$template_directory/machine-learning-model-version-update.json" \
    --parameters "uniqueId=${unique_id}" deployModels=true \
    --query properties.provisioningState -o tsv
