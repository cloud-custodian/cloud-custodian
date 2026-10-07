#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

if [[ $# -eq 0 ]]; then
    # If there is no arguments -- deploy everything
    cleanup_all=1
    skip_list=()
    cleanup_list=()
else
    if [[ $1 == "--skip" ]]; then
        # If we see option '--skip' -- deploy everything except for specific templates
        cleanup_all=1
        skip_list=("${@:2}")
        cleanup_list=()
    else
        # If there is no '--skip', deploy specific templates
        cleanup_all=0
        cleanup_list=("${@:1}")
        skip_list=()
    fi
fi

delete_resource() {
    echo "Delete for $filenameNoExtension started"
    fileName=${1##*/}
    filenameNoExtension=${fileName%.*}
    rgName="test_$filenameNoExtension"

    if [[ "$fileName" == "cost-management-export.json" ]]; then
        token=$(az account get-access-token --query accessToken --output tsv)
        url=https://management.azure.com/subscriptions/${AZURE_SUBSCRIPTION_ID}/providers/Microsoft.CostManagement/exports/cccostexport?api-version=2019-01-01
        curl -X DELETE -H "Authorization: Bearer ${token}" ${url}
    elif [[ "$fileName" == "budget.json" ]]; then
        token=$(az account get-access-token --query accessToken --output tsv)
        budget_base_url=https://management.azure.com/subscriptions/${AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Consumption/budgets
        curl -X DELETE -H "Authorization: Bearer ${token}" "${budget_base_url}/budget_1000?api-version=2023-05-01"
        curl -X DELETE -H "Authorization: Bearer ${token}" "${budget_base_url}/budget_1001?api-version=2023-05-01"
        az deployment sub delete --name cctest-budget --output None
    elif [[ "$fileName" == "cognitive-service-deployment.json" ]]; then
        account_name="${AZURE_OPENAI_ACCOUNT_NAME}"
        if [[ -z "${account_name}" ]]; then
            account_name=$(az cognitiveservices account list --resource-group $rgName --query [0].name --output tsv)
        fi
        if [[ -n "${account_name}" ]]; then
            az cognitiveservices account delete --resource-group $rgName --name $account_name --yes --output None
        fi
    elif [[ "$fileName" == "locked.json" ]]; then
        az lock delete --name cctestlockfilter --resource-group $rgName
        az lock delete --name rglock --resource-group $rgName
        sqlid=$(az sql server list -g test_locked --query [0].id --output tsv)
        az lock delete --ids "${sqlid}/providers/Microsoft.Authorization/locks/sqllock"
        dbid=$(az sql db list --ids $sqlid --query [0].id --output tsv)
        az lock delete --ids "${dbid}/providers/Microsoft.Authorization/locks/dblock"
        sleep 10s
    fi

    # Deleting the resource group only soft-deletes ML workspaces, which then
    # stay listed by the ML provider and break child enumeration. Purge them first.
    if [[ "$fileName" == machine-learning*.json ]]; then
        # A workspace can't be purged while it has online endpoints. Deleting
        # an endpoint also deletes its deployments.
        for endpoint in $(az resource list --resource-group $rgName \
            --resource-type Microsoft.MachineLearningServices/workspaces/onlineEndpoints \
            --query "[].id" --output tsv); do
            az rest --method delete \
                --url "https://management.azure.com${endpoint}?api-version=2025-06-01"
            az resource wait --deleted --ids "$endpoint" --timeout 1800
        done
        if ! workspaces=$(az resource list --resource-group "$rgName" \
            --resource-type Microsoft.MachineLearningServices/workspaces \
            --query "[].id" --output tsv); then
            echo "Failed to list Machine Learning workspaces; skipping delete of resource group $rgName"
            return 1
        fi
        for ws in $workspaces; do
            # Never fall back to the group delete if the purge fails, since
            # that soft-deletes the workspace instead.
            if ! az rest --method delete \
                    --url "https://management.azure.com${ws}?api-version=2025-06-01&forceToPurge=true" \
                || ! az resource wait --deleted --ids "$ws" --timeout 900; then
                echo "Failed to purge ${ws}; skipping delete of resource group $rgName"
                return 1
            fi
        done
    fi

    az group delete --name $rgName --yes --output None

    echo "Delete for $filenameNoExtension complete"
}

delete_acs() {
    echo "Delete for ACS started"
    rgName=test_containerservice
    az group delete --name $rgName --yes --no-wait
    echo "Delete for ACS complete"
}

delete_policy_assignment() {
    echo "Delete for policy assignment started"
    az policy assignment delete --name cctestpolicy
    echo "Delete for policy assignment complete"
}

delete_cognitive_services() {
    echo "Delete for cog services started"
    az resource delete --ids /subscriptions/${AZURE_SUBSCRIPTION_ID}/providers/Microsoft.CognitiveServices/locations/global/resourceGroups/test_cognitive-service/deletedAccounts/cctest-cog-serv
    echo "Delete for cog services complete"
}

function should_cleanup() {
    local item
    if [[ ${cleanup_all} -eq 1 ]]; then
        for item in "${skip_list[@]}"; do
            if [[ "$item" == "$1" ]]; then
                return 0
            fi
        done
        return 1
    else
        for item in "${cleanup_list[@]}"; do
            if [[ "$item" == "$1" ]]; then
                return 1
            fi
        done
        return 0
    fi
}

# Delete RG's for each template file
pids=()
jobs=()
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}

    should_cleanup "$filenameNoExtension"
    if [[ $? -eq 1 ]]; then
        delete_resource ${file} &
        pids+=($!)
        jobs+=("${filenameNoExtension}")
    fi
done

# Destroy ACS resource
should_cleanup "containerservice"
if [[ $? -eq 1 ]]; then
    delete_acs &
    pids+=($!)
    jobs+=("containerservice")
fi

should_cleanup "policy"
# Destroy Azure Policy Assignment
if [[ $? -eq 1 ]]; then
    delete_policy_assignment &
    pids+=($!)
    jobs+=("policy")
fi

should_cleanup "cognitive-service"
# Destroy Azure Cog Services Soft Delete
if [[ $? -eq 1 ]]; then
    delete_cognitive_services &
    pids+=($!)
    jobs+=("cognitive-service")
fi

# Wait until all cleanup is finished
failed=0
for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    job_name="${jobs[$i]}"
    if ! wait "$pid"; then
        echo "Cleanup job failed: ${job_name}"
        failed=1
    fi
done

if [[ "$failed" -ne 0 ]]; then
    exit 1
fi
