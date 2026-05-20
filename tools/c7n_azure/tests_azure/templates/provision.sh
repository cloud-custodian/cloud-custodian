#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

# If `az ad signed-in-user show` fails then update your Azure CLI version

# If you can't provision keyvault or cost-management-export resources please ensure you use
# your user account and not a Service Principals.
# cost-management-export: requires SP to have valid email claim
# keyvault: Managed Storage can't be provisioned with SP

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

print_failed_group_deployment() {
    rgName="$1"
    latest_deployment=$(az deployment group list \
        --resource-group "$rgName" \
        --query "[0].name" \
        --output tsv 2>/dev/null)
    if [[ -n "$latest_deployment" ]]; then
        echo "Last deployment '$latest_deployment' operations for resource group '$rgName':"
        az deployment group operation list \
            --resource-group "$rgName" \
            --name "$latest_deployment" \
            --query "[].{state:properties.provisioningState,status:properties.statusMessage}" \
            --output jsonc || true
    fi
}

if [[ $(az account show --query user.type --out tsv) == "user" ]]; then
    is_user=1
else
    is_user=0
fi

if [[ $# -eq 0 ]]; then
    # If there is no arguments -- deploy everything
    deploy_all=1
    skip_list=()
    deploy_list=()
else
    if [[ $1 == "--skip" ]]; then
        # If we see option '--skip' -- deploy everything except for specific templates
        deploy_all=1
        skip_list=("${@:2}")
        deploy_list=()
    else
        # If there is no '--skip', deploy specific templates
        deploy_all=0
        deploy_list=("${@:1}")
        skip_list=()
    fi
fi

deploy_resource() {
    fileName=${1##*/}
    filenameNoExtension=${fileName%.*}
    rgName="test_$filenameNoExtension"
    echo "Deployment for ${filenameNoExtension} started"

    az group create --name $rgName --location $resourceLocation --output None

    if [[ "$fileName" == "keyvault.json" ]]; then

        if [[ ${is_user} -ne 1 ]]; then
            echo "KeyVault can't be provisioned with Service Principal due to Keyvault Managed Storage Account restrictions"
            exit 1
        fi

        azureAdUserObjectId=$(az ad signed-in-user show --query id --output tsv)
        az deployment group create --resource-group $rgName --template-file $file \
            --parameters "userObjectId=$azureAdUserObjectId" --output None

        vault_name=$(az keyvault list --resource-group $rgName --query [0].name --output tsv)

        storage_id=$(az storage account list --resource-group ${rgName} --query [0].id --output tsv)

        az keyvault key create --vault-name ${vault_name} --name cctestrsa --kty RSA --output None
        az keyvault key create --vault-name ${vault_name} --name cctestec --kty EC --output None

        az keyvault certificate create --vault-name ${vault_name} --name cctest1 -p "$(az keyvault certificate get-default-policy)" --output None
        az keyvault certificate create --vault-name ${vault_name} --name cctest2 -p "$(az keyvault certificate get-default-policy)" --output None

     #   az role assignment create --role "Storage Account Key Operator Service Role" --assignee cfa8b339-82a2-471a-a3c9-0fc0be7a4093 --scope ${storage_id} --output None
        az keyvault storage add --vault-name ${vault_name} -n storage1 --active-key-name key1 --resource-id ${storage_id} --auto-regenerate-key True --regeneration-period P720D  --output None
        az keyvault storage add --vault-name ${vault_name} -n storage2 --active-key-name key2 --resource-id ${storage_id} --auto-regenerate-key False --output None

    elif [[ "$fileName" == "aks.json" ]]; then

        az deployment group create --resource-group $rgName --template-file $file --parameters client_id=$AZURE_CLIENT_ID client_secret=$AZURE_CLIENT_SECRET --mode Complete --output None

    elif [[ "$fileName" == "cognitive-service-deployment.json" ]]; then

        openai_location="${AZURE_OPENAI_LOCATION:-eastus}"
        model_name="${AZURE_OPENAI_MODEL_NAME:-gpt-4o-mini}"
        model_version="${AZURE_OPENAI_MODEL_VERSION:-2024-07-18}"
        deployment_name="${AZURE_OPENAI_DEPLOYMENT_NAME:-cctest-gpt4o-mini}"
        account_name="${AZURE_OPENAI_ACCOUNT_NAME}"

        if az cognitiveservices account show-deleted \
            --resource-group "$rgName" \
            --location "$openai_location" \
            --name "$account_name" \
            --output none 2>/dev/null; then
            echo "Found soft-deleted Cognitive Services account '${account_name}' in '${rgName}' (${openai_location})."
            echo "Purging soft-deleted account '${account_name}' before deployment."
            az cognitiveservices account purge \
                --resource-group "$rgName" \
                --location "$openai_location" \
                --name "$account_name" \
                --output none || {
                    echo "Failed to purge soft-deleted account '${account_name}'."
                    exit 1
                }
            sleep 10
            if az cognitiveservices account show-deleted \
                --resource-group "$rgName" \
                --location "$openai_location" \
                --name "$account_name" \
                --output none 2>/dev/null; then
                echo "Soft-deleted account '${account_name}' is still present after purge."
                exit 1
            fi
        fi

        az deployment group create \
            --resource-group $rgName \
            --template-file $file \
            --parameters accountName=$account_name location=$openai_location \
            --mode Complete \
            --output None || {
                echo "Failed to deploy Cognitive Services account '${account_name}' in resource group '${rgName}'."
                print_failed_group_deployment "$rgName"
                exit 1
            }

        account_ready=0
        for attempt in {1..6}; do
            if az cognitiveservices account show \
                --resource-group "$rgName" \
                --name "$account_name" \
                --output none 2>/dev/null; then
                account_ready=1
                break
            fi
            sleep 5
        done

        if [[ "$account_ready" -ne 1 ]]; then
            echo "Cognitive Services account '${account_name}' was not found after ARM deployment."
            print_failed_group_deployment "$rgName"
            exit 1
        fi

        if ! az cognitiveservices account deployment create \
            --resource-group $rgName \
            --name $account_name \
            --deployment-name $deployment_name \
            --model-format OpenAI \
            --model-name $model_name \
            --model-version $model_version \
            --sku-name Standard \
            --sku-capacity 1 \
            --output None; then
            echo "Failed to create Cognitive Services deployment ${deployment_name} in account ${account_name}"
            exit 1
        fi

        deployment_count=$(az cognitiveservices account deployment list \
            --resource-group $rgName \
            --name $account_name \
            --query "length(@)" \
            --output tsv)
        if [[ -z "$deployment_count" ]] || [[ "$deployment_count" -lt 1 ]]; then
            echo "No deployments found after provisioning for account ${account_name}"
            exit 1
        fi

    elif [[ "$fileName" == "cost-management-export.json" ]]; then

        if [[ ${is_user} -ne 1 ]]; then
            echo "Cost Management Export can't be provisioned with Service Principal due to Keyvault Managed Storage Account restrictions"
            exit 1
        fi

        # Deploy storage account required for the export
        az deployment group create --resource-group $rgName --template-file $file --mode Complete --output None

        token=$(az account get-access-token --query accessToken --output tsv)
        storage_id=$(az storage account list --resource-group $rgName --query [0].id --output tsv)
        subscription_id=$(az account show --query id --output tsv)
        url=https://management.azure.com/subscriptions/${subscription_id}/providers/Microsoft.CostManagement/exports/cccostexport?api-version=2019-01-01

        eval "echo \"$(cat cost-management-export-body.template)\"" > cost-management.body

        curl -X PUT -d "@cost-management.body" -H "content-type: application/json" -H "Authorization: Bearer ${token}" ${url}

        rm -f cost-management.body

    else
        az deployment group create --resource-group $rgName --template-file $file --mode Complete --output None
    fi

    if [[ "$fileName" == "cosmosdb.json" ]]; then
        ip=$(curl -s https://checkip.amazonaws.com)
        allow_list="$ip,104.42.195.92,40.76.54.131,52.176.6.30,52.169.50.45,52.187.184.26"
        sub_id=$(az account show --query id --output tsv)
        suffix="${sub_id:${#sub_id} - 12}"
        echo "Adding local external IP (${ip}) and azure portals to cosmos firewall allow list..."
        az cosmosdb update -g $rgName -n cctestcosmosdb$suffix --ip-range-filter $allow_list
    fi

    echo "Deployment for ${filenameNoExtension} complete"
}

deploy_acs() {
    rgName=test_containerservice
    echo "Deployment for ACS started"
    az group create --name $rgName --location $resourceLocation --output None
    az acs create -n cctestacs -d cctestacsdns -g $rgName --generate-ssh-keys --orchestrator-type kubernetes --output None
    echo "Deployment for ACS complete"
}

deploy_policy_assignment() {
    echo "Deployment for policy assignment started"
    # 06a78e20-9358-41c9-923c-fb736d382a4d is an id for 'Audit VMs that do not use managed disks' policy
    az policy assignment create --display-name cctestpolicy --name cctestpolicy --policy '06a78e20-9358-41c9-923c-fb736d382a4d' --output None
    echo "Deployment for policy assignment complete"
}

function should_deploy() {
    local item
    if [[ ${deploy_all} -eq 1 ]]; then
        for item in "${skip_list[@]}"; do
            if [[ "$item" == "$1" ]]; then
                return 0
            fi
        done
        return 1
    else
        for item in "${deploy_list[@]}"; do
            if [[ "$item" == "$1" ]]; then
                return 1
            fi
        done
        return 0
    fi
}

# Ensure AZURE_CLIENT_ID and AZURE_CLIENT_SECRET are available for AKS deployment
should_deploy "aks"
if [[ $? -eq 1 ]]; then
    if [[ -z "$AZURE_CLIENT_ID" ]] || [[ -z "$AZURE_CLIENT_SECRET" ]]; then
        echo "AZURE_CLIENT_ID AND AZURE_CLIENT_SECRET environment variables are required to deploy AKS"
        exit 1
    fi
fi

# Create resource groups and deploy for each template file
pids=()
jobs=()
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}
    should_deploy "$filenameNoExtension"
    if [[ $? -eq 1 ]]; then
        deploy_resource ${file} &
        pids+=($!)
        jobs+=("${filenameNoExtension}")
    fi
done

# Provision non-arm resources
should_deploy "containerservice"
if [[ $? -eq 1 ]]; then
    deploy_acs &
    pids+=($!)
    jobs+=("containerservice")
fi

should_deploy "policy"
if [[ $? -eq 1 ]]; then
    deploy_policy_assignment &
    pids+=($!)
    jobs+=("policy")
fi

# Wait until all deployments are finished
failed=0
for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    job_name="${jobs[$i]}"
    if ! wait "$pid"; then
        echo "Deployment job failed: ${job_name}"
        failed=1
    fi
done

if [[ "$failed" -ne 0 ]]; then
    exit 1
fi
