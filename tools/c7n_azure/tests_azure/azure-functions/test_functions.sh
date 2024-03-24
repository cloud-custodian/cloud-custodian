#!/bin/bash

set -e

rg_name=cloud-custodian-test-functions-$RANDOM
rg_identity_name="${rg_name}-identity"
identity_name="c7n-identity"

function cleanup {
    set +e
    rm -f policies.yaml
    echo "Removing resource groups"
    $(az group delete -n ${rg_name} -y)
    $(az group delete -n ${rg_name}-dedicated -y)
    $(az group delete -n ${rg_name}-consumption -y)
    $(az group delete -n ${rg_identity_name}-consumption -y)
}
trap cleanup EXIT

echo "Logging in to Azure"
az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET -t $AZURE_TENANT_ID -o none
az account set -s $AZURE_SUBSCRIPTION_ID -o none

echo "Creating user managed identity"
az group create -l westus -n ${rg_identity_name} -o none
identity_principal=$(az identity create -g ${rg_identity_name} --name ${identity_name} --query clientId -o tsv)
sleep 60
az role assignment create --assignee-object-id ${identity_principal} --assignee-principal-type "ServicePrincipal" --role "Owner" --scope "/subscriptions/${AZURE_SUBSCRIPTION_ID}" -o None

eval "echo \"$(cat templates/policies.yaml)\"" > policies.yaml

echo "Running Cloud Custodian"
custodian run -s=/dev/null policies.yaml

echo "Creating new resource group"
az group create -l westus -n ${rg_name} -o none

result=1
max_attempts=60

echo "Waiting for the 'custodian-function-test: passed' tag..."
for i in $(seq 1 ${max_attempts})
do
    sleep 30s
    echo "Attempt ${i}/${max_attempts}..."
    tags=$(az group show -n ${rg_name} --query 'tags' -o json)
    echo ${tags}
    if [[ $(echo $tags | grep -o 'custodian-function-' | wc -l) -eq 4 ]]; then
        result=0
        echo "Found all expected tags."
        break
    fi
    echo "Tag not found, retrying in 30 seconds."
done

echo "Exiting... Status:${result}"
exit ${result}
