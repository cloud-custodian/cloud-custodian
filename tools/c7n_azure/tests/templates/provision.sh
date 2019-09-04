#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

# If `az ad signed-in-user show` fails then update your Azure CLI version

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

if [ $# -eq 0 ] || [[ "$@" =~ "aks" ]]; then
    if [[ -z "$AZURE_CLIENT_ID" ]] || [[ -z "$AZURE_CLIENT_SECRET" ]]; then
        echo "AZURE_CLIENT_ID AND AZURE_CLIENT_SECRET environment variables are required to deploy AKS"
        exit 1
    fi
fi

deploy_resource() {
    echo "Deployment for ${filenameNoExtension} started"

    fileName=${1##*/}
    filenameNoExtension=${fileName%.*}
    rgName="test_$filenameNoExtension"

    az group create --name $rgName --location $resourceLocation --output None

    if [[ "$fileName" == "keyvault.json" ]]; then

        azureAdUserObjectId=$(az ad signed-in-user show --query objectId --output tsv)

        az group deployment create --resource-group $rgName --template-file $file \
            --parameters "userObjectId=$azureAdUserObjectId" --output None

        vault_name=$(az keyvault list --resource-group $rgName --query [0].name --output tsv)

        storage_id=$(az storage account list --resource-group ${rgName} --query [0].id --output tsv)

        az keyvault key create --vault-name ${vault_name} --name cctestrsa --kty RSA --output None
        az keyvault key create --vault-name ${vault_name} --name cctestec --kty EC --output None

        az keyvault certificate create --vault-name ${vault_name} --name cctest1 -p "$(az keyvault certificate get-default-policy)" --output None
        az keyvault certificate create --vault-name ${vault_name} --name cctest2 -p "$(az keyvault certificate get-default-policy)" --output None

        az role assignment create --role "Storage Account Key Operator Service Role" --assignee cfa8b339-82a2-471a-a3c9-0fc0be7a4093 --scope ${storage_id} --output None
        az keyvault storage add --vault-name ${vault_name} -n storage1 --active-key-name key1 --resource-id ${storage_id} --auto-regenerate-key True --regeneration-period P180D  --output None
        az keyvault storage add --vault-name ${vault_name} -n storage2 --active-key-name key2 --resource-id ${storage_id} --auto-regenerate-key False --output None

    elif [[ "$fileName" == "aks.json" ]]; then

        az group deployment create --resource-group $rgName --template-file $file --parameters client_id=$AZURE_CLIENT_ID client_secret=$AZURE_CLIENT_SECRET --mode Complete --output None

    elif [[ "$fileName" == "cost-management-export.json" ]]; then

        # Deploy storage account required for the export
        az group deployment create --resource-group $rgName --template-file $file --mode Complete --output None

        token=$(az account get-access-token --query accessToken --output tsv)
        storage_id=$(az storage account list --resource-group $rgName --query [0].id --output tsv)
        subscription_id=$(az account show --query id --output tsv)
        url=https://management.azure.com/subscriptions/${subscription_id}/providers/Microsoft.CostManagement/exports/cccostexport?api-version=2019-01-01

        eval "echo \"$(cat cost-management-export-body.template)\"" > cost-management.body

        curl -X PUT -d "@cost-management.body" -H "content-type: application/json" -H "Authorization: Bearer ${token}" ${url}

        rm -f cost-management.body

    else
        az group deployment create --resource-group $rgName --template-file $file --mode Complete --output None
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

# Create resource groups and deploy for each template file
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}

    if [ $# -eq 0 ] || [[ "$@" =~ "$filenameNoExtension" ]]; then
        deploy_resource ${file} &
    fi
done

if [ $# -eq 0 ] || [[ "$@" =~ "containerservice" ]]; then
    deploy_acs &
fi

if [ $# -eq 0 ] || [[ "$@" =~ "policyassignment" ]]; then
    deploy_policy_assignment &
fi

# Wait until all deployments are finished
wait
