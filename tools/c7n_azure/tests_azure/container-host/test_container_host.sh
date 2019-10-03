#!/usr/bin/env bash

set -ex
export AZURE_CORE_OUTPUT="none"

test_rg_name="custodian-container-host-nightly-subject"

function cleanup {
    set +ex
    # TODO: delete the resource group with everything in it
    unset AZURE_CORE_OUTPUT
}
trap cleanup EXIT

az login --service-principal --username $AZURE_CLIENT_ID --password $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID
az account set --subscription $AZURE_SUBSCRIPTION_ID

##################################### Shared Infrastructure ########################################

# Resource Group
resource_group_name="custodian-container-host-nightly"
location="westus2"
az group create --name $resource_group_name --location $location

# Storage Account
storage_account_name="c7ncontainernightly"
az storage account create --resource-group $resource_group_name --name $storage_account_name
storage_account_key=$(az storage account keys list --account-name $storage_account_name --query "[0].value" --output tsv)
read -r storage_account_id storage_blob_endpoint <<<$(az storage account show --name $storage_account_name --query "{id: id, blobEndpoint: primaryEndpoints.blob}" --output tsv)

# Application Insights
app_insights_name="custodian-insights"
az extension add --name application-insights
az monitor app-insights component create --resource-group $resource_group_name --app $app_insights_name --location $location
instrumentation_key="azure://$(az monitor app-insights component show --resource-group $resource_group_name --app $app_insights_name --query "instrumentationKey" --output tsv)"

# Prepare the storage account for a Container Host
#   $1: host mode (aci or aks)
#   $2: policy container name
#   $3: log container name
function setup-storage-account {
    az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $2
    az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $3

    sed -e "s;%RG_NAME%;$test_rg_name;g" -e "s;%HOST_MODE%;$1;g" policies.yaml > policies-$1.yaml
    az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $2 --file policies-$1.yaml --name policies-$1.yaml
    rm policies-$1.yaml
}

############################################ ACI ###################################################

aci_name="custodian-aci"
aci_queue_name="aci-queue"
policy_container_name="policies-aci"
log_container_name="logs-aci"

# Managed Identity
uai_name="custodian-aci"
az identity create --resource-group $resource_group_name --name $uai_name
sleep 60  # Give some time for the identity to propagate

# Role Assignments
uai_object_id=$(az identity show --resource-group $resource_group_name --name $uai_name --query "principalId" --output tsv)
az role assignment create --assignee-object-id $uai_object_id --role "Contributor" --scope /subscriptions/$AZURE_SUBSCRIPTION_ID
az role assignment create --assignee-object-id $uai_object_id --role "Storage Blob Data Contributor" --scope $storage_account_id
az role assignment create --assignee-object-id $uai_object_id --role "Storage Queue Data Contributor" --scope $storage_account_id

# Populate Storage Account
setup-storage-account aci $policy_container_name $log_container_name

# Deploy Container Host
az group deployment create --resource-group $resource_group_name --template-file ../../../ops/azure/container-host/aci/aci-template.json --parameters \
    aci_name=$aci_name \
    user_assigned_identity_name=$uai_name \
    azure_subscription_id=$AZURE_SUBSCRIPTION_ID \
    azure_container_queue_name=$aci_queue_name \
    azure_container_policy_uri="$storage_blob_endpoint$policy_container_name" \
    azure_container_storage_resource_id=$storage_account_id \
    azure_container_log_group=$instrumentation_key \
    azure_container_metrics=$instrumentation_key \
    azure_container_output_dir="${storage_blob_endpoint/#https/azure}$log_container_name"

############################################ AKS ###################################################

aks_name="custodian-aks"
policy_container_name="policies-aks"
log_container_name="logs-aks"

# Storage Permissions
az role assignment create --assignee $AZURE_CLIENT_ID --role "Storage Blob Data Contributor" --scope $storage_account_id
az role assignment create --assignee $AZURE_CLIENT_ID --role "Storage Queue Data Contributor" --scope $storage_account_id

# Populate Storage Account
setup-storage-account aks $policy_container_name $log_container_name

# AKS & Helm Init
az aks create --resource-group $resource_group_name --name $aks_name --node-count 1 --node-vm-size Standard_B2s --service-principal $AZURE_CLIENT_ID --client-secret $AZURE_CLIENT_SECRET 
az aks get-credentials --resource-group $resource_group_name --name $aks_name --overwrite-existing
kubectl apply -f rbac-config.yaml > /dev/null
helm init --service-account tiller --wait > /dev/null

# Helm Deployment
cat <<EOF > helm-values.yaml
defaultEnvironment:
  AZURE_TENANT_ID: "$AZURE_TENANT_ID"
  AZURE_CLIENT_ID: "$AZURE_CLIENT_ID"
  AZURE_CONTAINER_POLICY_URI: "$storage_blob_endpoint$policy_container_name"
  AZURE_CONTAINER_STORAGE_RESOURCE_ID: "$storage_account_id"
  AZURE_CONTAINER_METRICS: "$instrumentation_key"
  AZURE_CONTAINER_LOG_GROUP: "$instrumentation_key"
  AZURE_CONTAINER_OUTPUT_DIR: "${storage_blob_endpoint/#https/azure}$log_container_name"

subscriptionHosts:
  - name: "container-host"
    environment:
      AZURE_SUBSCRIPTION_ID: "$AZURE_SUBSCRIPTION_ID"
EOF
helm upgrade --install --wait --namespace $aks_name \
    --values helm-values.yaml \
    --set defaultSecretEnvironment.AZURE_CLIENT_SECRET=$(base64 <<< $AZURE_CLIENT_SECRET) \
    $aks_name ../../../ops/azure/container-host/chart > /dev/null
rm -f helm-values.yaml

################################## Trigger Policies ################################################

# At this point, the container host is running in both ACI and AKS.
# Once this test resource group is created, then each host should tag the group when created and every minute.
# So, we are looking for 4 tags:
#
#   1. ACI event based (c7n-aci-event)
#   1. ACI periodic (c7n-aci-periodic)
#   1. AKS event based (c7n-aks-event)
#   1. AKS periodic (c7n-aks-periodic)

az group create --name $test_rg_name --location $location
sleep 75

# Check for all 4 of these tags with the value "passed"

