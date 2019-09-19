#!/bin/bash

set -e

function cleanup {
    set +e
}
trap cleanup EXIT

echo "Logging in to Azure"
az login --service-principal --username $AZURE_CLIENT_ID --password $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID --output none
az account set --subscription $AZURE_SUBSCRIPTION_ID --output none

echo "Creating Shared Infrastructure"

resource_group_name="custodian-container-host-nightly"
location="westus2"
storage_account_name="c7ncontainernightly"
policy_container_name="policies"
log_container_name="logs"
app_insights_name="custodian-insights"

echo "  > creating resource group"
az group create --name $resource_group_name --location $location --output none

echo "  > creating storage account"
az storage account create --resource-group $resource_group_name --name $storage_account_name --output none
storage_account_key=$(az storage account keys list --account-name $storage_account_name --query "[0].value" --output tsv)
storage_account_id=$(az storage account show --name $storage_account_name --query "id" --output tsv)
storage_blob_endpoint=$(az storage account show --resource-group $resource_group_name --name $storage_account_name --query "primaryEndpoints.blob" --output tsv)
policy_uri="$storage_blob_endpoint$policy_container_name"
log_uri="${storage_blob_endpoint/#https/azure}$log_container_name"

function grant-storage-permissions {
    storage_roles=("Contributor" "Storage Blob Data Contributor" "Storage Queue Data Contributor")
    for role in ${storage_roles[@]}; do
        az role assignment create --assignee $1 --role $role --scope $storage_account_id
    done
}

echo "    > creating policy container"
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $policy_container_name --output none

echo "    > creating log container"
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $log_container_name --output none

echo "  > uploading test policies"
sed \
    -e "s;%RG_NAME%;$resource_group_name;g" \
    policies.yaml > policies-rendered.yaml
az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $policy_container_name --file policies-rendered.yaml --name policies.yaml --output none
rm policies-rendered.yaml

echo "  > creating app insights"
az extension add --name application-insights
az monitor app-insights component create --resource-group $resource_group_name --app $app_insights_name --location $location --output none
instrumentation_key="azure://$(az monitor app-insights component show --resource-group $resource_group_name --app $app_insights_name --query "instrumentationKey" --output tsv)"

echo "Deploying to ACI"

uai_name="custodian-aci"
az identity create --resource-group $resource_group_name --name $uai_name --output none
uai_client_id=$(az identity show --resource-group $resource_group_name --name $uai_name --query "clientId" --output tsv)
grant-storage-permissions $uai_client_id

aci_name="custodian-aci"
aci_queue_name="aci-queue"

az group deployment create --resource-group $resource_group_name --template-file ../../../ops/azure/container-host/aci/aci-template.json --parameters \
    aci_name=$aci_name \
    user_assigned_identity_name=$uai_name \
    azure_subscription_id=$AZURE_SUBSCRIPTION_ID \
    azure_container_queue_name=$aci_queue_name \
    azure_container_policy_uri=$policy_uri \
    azure_container_storage_resource_id=$storage_account_id \
    azure_container_log_group=$instrumentation_key \
    azure_container_metrics=$instrumentation_key \
    azure_container_output_dir=$log_uri

echo "Deploying to AKS"

echo "Done"
