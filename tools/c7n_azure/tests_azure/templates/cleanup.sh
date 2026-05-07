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
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}

    should_cleanup "$filenameNoExtension"
    if [[ $? -eq 1 ]]; then
        delete_resource ${file} &
    fi
done

# Destroy ACS resource
should_cleanup "containerservice"
if [[ $? -eq 1 ]]; then
    delete_acs &
fi

should_cleanup "policy"
# Destroy Azure Policy Assignment
if [[ $? -eq 1 ]]; then
    delete_policy_assignment &
fi

should_cleanup "cognitive-service"
# Destroy Azure Cog Services Soft Delete
if [[ $? -eq 1 ]]; then
    delete_cognitive_services &
fi

# Wait until all cleanup is finished
wait
