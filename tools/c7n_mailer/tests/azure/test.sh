#!/bin/bash

set -e
set -x

location=eastus
rg_name=cloud-custodian-test-mailer$RANDOM
storage_name=custodianstorage$RANDOM
queue_name=mailer-queue

username=${SENDGRID_USERNAME}
password=${SENDGRID_PASSWORD}
smtp_server=smtp.sendgrid.net

function cleanup {
    set +e
    rm -f mailer.yaml
    rm -f notify_policy.yaml
    rm -rf azure-notify
    echo "Removing resource group"
    az group delete -n ${rg_name} -y -o None
}
trap cleanup EXIT

az login --service-principal --username ${AZURE_CLIENT_ID} --password ${AZURE_CLIENT_SECRET} --tenant ${AZURE_TENANT_ID} -o None
az account set -s ${AZURE_SUBSCRIPTION_ID} -o None

az group create -n ${rg_name} -l ${location} -o none
storage_id=$(az storage account create -g ${rg_name} -l ${location} -n ${storage_name} --query id -o tsv)
az storage queue create -n ${queue_name} --account-name ${storage_name} -o none
az role assignment create --role "Storage Queue Data Contributor" --assignee ${AZURE_CLIENT_ID} --scope ${storage_id} -o None

# Ensure role assignment is updated
sleep 10s

# Render custodian configuration
eval "echo \"$(cat templates/mailer.yaml)\"" > mailer.yaml
eval "echo \"$(cat templates/mailer_sendgrid.yaml)\"" > mailer_sendgrid.yaml
eval "echo \"$(cat templates/notify_policy.yaml)\"" > notify_policy.yaml

r=$(curl -X "GET" "https://api.sendgrid.com/api/stats.get.json?api_user=${username}&api_key=${password}&days=1&aggregate=1")
requests_expected=$(($(echo $r | grep -Po '"requests":\s*\d*,' | grep -Po '\d*')+3))

# Run custodian
# Test sendgrid delivery
custodian run -s=. notify_policy.yaml
c7n-mailer -c mailer_sendgrid.yaml --run

# Test SMTP delivery
custodian run -s=. notify_policy.yaml
c7n-mailer -c mailer.yaml --run

# Test Azure Functions
custodian run -s=. notify_policy.yaml
c7n-mailer -c mailer.yaml --update-lambda

result=1
max_attempts=90

for i in $(seq 1 ${max_attempts})
do
    sleep 30s
    echo "Query sendgrid..."

    r=$(curl -X "GET" "https://api.sendgrid.com/api/stats.get.json?api_user=${username}&api_key=${password}&days=1&aggregate=1")
    requests=$(echo $r | grep -Po '"requests":\s*\d*,' | grep -Po '\d*')

    echo "Number of requests from sendgrid: $requests"

    if [[ ${requests} -eq ${requests_expected} ]]; then
        result=0
        break
    fi
done

echo "Exit status:${result}"
exit ${result}
