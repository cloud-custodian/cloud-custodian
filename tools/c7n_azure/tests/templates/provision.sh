#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

# If `az ad signed-in-user show` fails then update your Azure CLI version

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

azureTenantId=$(az account show --query tenantId)
azureTenantId=${azureTenantId//\"}

# Create resource groups and deploy for each template file
for file in "$templateDirectory"/*.json; do
  fileName=${file##*/}
  filenameNoExtension=${fileName%.*}
  rgName="test_$filenameNoExtension"

  if [ $# -eq 0 ] || [[ "$@" =~ "$filenameNoExtension" ]]; then

      az group create --name $rgName --location $resourceLocation
      if [[ "$filenameNoExtension" =~ "keyvault-no-policies" ]]; then
        az group deployment create --resource-group $rgName --template-file $file \
            --parameters "tenantId=$azureTenantId"
      elif [[ "$filenameNoExtension" =~ "keyvault" ]]; then
        azureAdUserObjectId=$(az ad signed-in-user show --query objectId)
        azureAdUserObjectId=${azureAdUserObjectId//\"}

        az group deployment create --resource-group $rgName --template-file $file \
            --parameters "tenantId=$azureTenantId" \
                         "userObjectId=$azureAdUserObjectId"

        vault_name=$(az keyvault list --resource-group $rgName --query [0].name | tr -d '"')

        storage_id=$(az storage account list --resource-group ${rgName} --query [0].id --out tsv)

        az keyvault key create --vault-name ${vault_name} --name cctestrsa --kty RSA
        az keyvault key create --vault-name ${vault_name} --name cctestec --kty EC

        az keyvault certificate create --vault-name ${vault_name} --name cctest1 -p "$(az keyvault certificate get-default-policy)"
        az keyvault certificate create --vault-name ${vault_name} --name cctest2 -p "$(az keyvault certificate get-default-policy)"

        az role assignment create --role "Storage Account Key Operator Service Role" --assignee cfa8b339-82a2-471a-a3c9-0fc0be7a4093 --scope ${storage_id}
        az keyvault storage add --vault-name ${vault_name} -n storage1 --active-key-name key1 --resource-id ${storage_id} --auto-regenerate-key True --regeneration-period P180D
        az keyvault storage add --vault-name ${vault_name} -n storage2 --active-key-name key2 --resource-id ${storage_id} --auto-regenerate-key False

      elif [[ "$filenameNoExtension" =~ "aks" ]]; then
        az group deployment create --resource-group $rgName --template-file $file --parameters client_id=$AZURE_CLIENT_ID client_secret=$AZURE_CLIENT_SECRET --mode Complete --no-wait
      else
        az group deployment create --resource-group $rgName --template-file $file --mode Complete --no-wait
      fi
  else
    echo "Skipping $rgName"
  fi
done

# Deploy ACS resource
rgName=test_containerservice
if [ $# -eq 0 ] || [[ "$@" =~ "containerservice" ]]; then
  az group create --name $rgName --location $resourceLocation
  az acs create -n cctestacs -d cctestacsdns -g $rgName --generate-ssh-keys --orchestrator-type kubernetes
else
  echo "Skipping $rgName"
fi

# Deploy Azure Policy Assignment
if [ $# -eq 0 ] || [[ "$@" =~ "policyassignment" ]]; then
  # 06a78e20-9358-41c9-923c-fb736d382a4d is an id for 'Audit VMs that do not use managed disks' policy
  az policy assignment create --display-name cctestpolicy --name cctestpolicy --policy '06a78e20-9358-41c9-923c-fb736d382a4d'
else
  echo "Skipping policyassignment"
fi

