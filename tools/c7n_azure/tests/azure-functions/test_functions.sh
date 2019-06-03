#!/bin/bash

set -e

function cleanup {
    set +e
    echo "Removing resource groups"
    $(az group delete -n custodian-function-test-rg -y)
    $(az group delete -n custodian-function-test-dedicated -y)
    $(az group delete -n custodian-function-test-consumption -y)
}
trap cleanup EXIT

echo "Logging to Azure"
az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET -t $AZURE_TENANT_ID -o none
az account set -s $AZURE_SUBSCRIPTION_ID -o none

echo "Running Cloud Custodian"
custodian run -s=/dev/null policy_timer_dedicated.yaml
custodian run -s=/dev/null policy_event_dedicated.yaml
custodian run -s=/dev/null policy_timer_consumption.yaml
custodian run -s=/dev/null policy_event_consumption.yaml

echo "Creating new resource group"
az group create -l westus -n custodian-function-test-rg -o none

result=1
max_attempts=60

echo "Waiting for the 'custodian-function-test: passed' tag..."
for i in $(seq 1 ${max_attempts})
do
    sleep 30s
    echo "Attempt ${i}/${max_attempts}..."
    tags=$(az group show -n custodian-function-test-rg --query 'tags' -o json)
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
