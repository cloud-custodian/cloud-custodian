#!/usr/bin/env bash

set -ex
export AZURE_CORE_OUTPUT="none"

function cleanup {
    set +ex
    # TODO: clean up
    unset AZURE_CORE_OUTPUT
}
trap cleanup EXIT

echo "Logging in to Azure"
az login --service-principal --username $AZURE_CLIENT_ID --password $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID
az account set --subscription $AZURE_SUBSCRIPTION_ID

##################################### Shared Infrastructure ########################################
echo "################################## Creating Shared Resources #######################################"

# Resource Group
echo "Creating Resource Group"
resource_group_name="custodian-container-host-nightly"
location="westus2"
az group create --name $resource_group_name --location $location

# Storage Account
echo "Creating Storage Account"
storage_account_name="c7ncontainernightly"
az storage account create --resource-group $resource_group_name --name $storage_account_name
storage_account_key=$(az storage account keys list --account-name $storage_account_name --query "[0].value" --output tsv)
read -r storage_account_id storage_blob_endpoint <<<$(az storage account show --name $storage_account_name --query "{id: id, blobEndpoint: primaryEndpoints.blob}" --output tsv)

# Application Insights
echo "Creating Application Insights"
app_insights_name="custodian-insights"
az extension add --name application-insights
az monitor app-insights component create --resource-group $resource_group_name --app $app_insights_name --location $location
instrumentation_key="azure://$(az monitor app-insights component show --resource-group $resource_group_name --app $app_insights_name --query "instrumentationKey" --output tsv)"

############################################ ACI ###################################################
echo "################################## Creating ACI Resources ##########################################"

aci_name="custodian-aci"
aci_queue_name="aci-queue"
aci_policy_container_name="policies-aci"
aci_log_container_name="logs-aci"

# Managed Identity
echo "Creating a Managed Identity"
uai_name="custodian-aci"
az identity create --resource-group $resource_group_name --name $uai_name
sleep 60  # Give some time for the identity to propagate

# Role Assignments
echo "Assigning Roles to the Managed Identity"
uai_object_id=$(az identity show --resource-group $resource_group_name --name $uai_name --query "principalId" --output tsv)
az role assignment create --assignee-object-id $uai_object_id --role "Contributor" --scope /subscriptions/$AZURE_SUBSCRIPTION_ID
az role assignment create --assignee-object-id $uai_object_id --role "Storage Blob Data Contributor" --scope $storage_account_id
az role assignment create --assignee-object-id $uai_object_id --role "Storage Queue Data Contributor" --scope $storage_account_id

# Populate Storage Account
echo "Populating Storage Acount"
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $aci_policy_container_name
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $aci_log_container_name
az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $aci_policy_container_name --file aci-periodic-policy.yaml --name aci-periodic-policy.yaml
az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $aci_policy_container_name --file aci-event-policy.yaml --name aci-event-policy.yaml

# Deploy Container Host
echo "Deploying Container Host in ACI"
az group deployment create --resource-group $resource_group_name --template-file ../../../ops/azure/container-host/aci/aci-template.json --parameters \
    aci_name=$aci_name \
    user_assigned_identity_name=$uai_name \
    azure_subscription_id=$AZURE_SUBSCRIPTION_ID \
    azure_container_queue_name=$aci_queue_name \
    azure_container_policy_uri="$storage_blob_endpoint$aci_policy_container_name" \
    azure_container_storage_resource_id=$storage_account_id \
    azure_container_log_group=$instrumentation_key \
    azure_container_metrics=$instrumentation_key \
    azure_container_output_dir="${storage_blob_endpoint/#https/azure}$aci_log_container_name"

############################################ AKS ###################################################
echo "################################## Creating AKS Resources ##########################################"

aks_name="custodian-aks"
aks_policy_container_name="policies-aks"
aks_log_container_name="logs-aks"

# Storage Permissions
echo "Assigning Storage Permissions"
az role assignment create --assignee $AZURE_CLIENT_ID --role "Storage Blob Data Contributor" --scope $storage_account_id
az role assignment create --assignee $AZURE_CLIENT_ID --role "Storage Queue Data Contributor" --scope $storage_account_id

# Populate Storage Account
echo "Populating Storage Account"
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $aks_policy_container_name
az storage container create --account-name $storage_account_name --account-key $storage_account_key --name $aks_log_container_name
az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $aks_policy_container_name --file aks-periodic-policy.yaml --name aks-periodic-policy.yaml
az storage blob upload --account-name $storage_account_name --account-key $storage_account_key --container-name $aks_policy_container_name --file aks-event-policy.yaml --name aks-event-policy.yaml

# AKS
echo "Creating AKS Cluster"
az aks create --resource-group $resource_group_name --name $aks_name --node-count 1 --node-vm-size Standard_B2s --service-principal $AZURE_CLIENT_ID --client-secret $AZURE_CLIENT_SECRET 

# Helm Init
echo "Initializing Helm"
az aks get-credentials --resource-group $resource_group_name --name $aks_name --overwrite-existing
kubectl apply -f rbac-config.yaml > /dev/null
helm init --service-account tiller --wait > /dev/null

# Helm Deployment
echo "Deploying Container Host with Helm Chart"
cat <<EOF > helm-values.yaml
defaultEnvironment:
  AZURE_TENANT_ID: "$AZURE_TENANT_ID"
  AZURE_CLIENT_ID: "$AZURE_CLIENT_ID"
  AZURE_CONTAINER_POLICY_URI: "$storage_blob_endpoint$aks_policy_container_name"
  AZURE_CONTAINER_STORAGE_RESOURCE_ID: "$storage_account_id"
  AZURE_CONTAINER_METRICS: "$instrumentation_key"
  AZURE_CONTAINER_LOG_GROUP: "$instrumentation_key"
  AZURE_CONTAINER_OUTPUT_DIR: "${storage_blob_endpoint/#https/azure}$aks_log_container_name"

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
echo "################################## Triggering Policies ################################################"

# Create a resource group for each test policy
echo "Creating Resource Groups Subjects for Policies"
rg_tests=("aci-periodic" "aci-event" "aks-periodic" "aks-event")
declare -A rg_test_results
for rg_test in "${rg_tests[@]}"; do
    az group create --location $location --name "container-host-nightly-$rg_test"
    rg_test_results[$rg_test]="pending"
done

echo "Press 'enter' to start validating"
read

# Check that each policy has run
echo "Verifying Tags from Policy Runs"
all_passed=false
max_attempts=60
for i in $(seq 1 $max_attempts); do 
    sleep 30
    echo "  attempt $i of $max_attempts"
    for rg_test in "${rg_tests[@]}"; do
        rg_test_results[$rg_test]=$(az group show --name "container-host-nightly-$rg_test" --query "tags.\"c7n-$rg_test\"")
    done

    all_passed=true
    for result in "${rg_test_results[@]}"; do
        if [[ $result -ne "passed" ]]; then all_passed=false; fi
    done
    if [[ all_passed -eq true ]]; then break; fi
    echo "Trying again in 30 seconds..."
done

if [[ all_passed -ne true ]]; then
    echo "Some policies failed to run"
    for rg_test in "${rg_tests[@]}"; do
        echo "  $rg_test: ${rg_test_results[$rg_test]}"
    done
    exit 1
fi
echo "All policies ran"

################################## Check Storage Output ############################################
echo "################################# Checking Storage Output ##########################################"

aci_output=$(az blob list --account-name $storage_account_name --account-key $storage_account_key --container-name $aci_log_container_name --query "[].name" --output tsv)
aks_output=$(az blob list --account-name $storage_account_name --account-key $storage_account_key --container-name $aks_log_container_name --query "[].name" --output tsv)
output_blobs="${aci_output[@]} ${aks_output[@]}"

for rg_test in $rg_tests; do
    echo "Checking for $rg_test output"
    entries=$(grep -o "c7n-$rg_test" <<< "${output_blobs[@]}" | wc -l)
    if [[ $entries -eq 0 ]]; then
        echo "Failed to find any output for $rg_test"
        exit 1
    fi
done

####################################### Check Metrics And Logs #####################################
echo "##################################### Checking Metrics And Logs ####################################"

logs_query="traces | extend policy = tostring(customDimensions[\"Policy\"]) | project policy, message | where message contains \"count:1\""
policy_logs=$(az monitor app-insights query --resource-group $resource_group_name --app $app_insights_name \
    --analytics-query $logs_query --offset 24h --query 'tables[0].rows' --output tsv)

metrics_query="customMetrics | where name == \"ResourceCount\" and value == 1 | extend policy = tostring(customDimensions[\"Policy\"]) | project policy, value"
resource_counts=$(az monitor app-insights query --app $app_insights_name \
    --analytics-query $metrics_query --offset 24h --query 'tables[0].rows' --output tsv)

for rg_test in $rg_tests; do
    log_line=$(grep c7n-$rg_test <<< $policy_logs | wc -l)
    if [[ $log_line -ne 1 ]]; then
        echo "Failed to find log line for $rg_test"
        exit 1
    fi
    resource_count_line=$(grep c7n-$rg_test <<< $resource_counts | wc -l)
    if [[ $resource_count_line -ne 1 ]]; then
        echo "Failed to find resource count for $rg_test"
        exit 1
    fi
done

echo "Done!"
