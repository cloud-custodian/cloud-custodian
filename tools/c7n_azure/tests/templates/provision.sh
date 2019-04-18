#!/bin/bash
IFS=$'\n\t'


# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

azureTenantId=$(az account show --query tenantId)
azureTenantId=${azureTenantId//\"}
azureAdUserObjectId=$(az ad signed-in-user show --query objectId)
azureAdUserObjectId=${azureAdUserObjectId//\"}

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
        az group deployment create --resource-group $rgName --template-file $file \
            --parameters "tenantId=$azureTenantId" \
                         "userObjectId=$azureAdUserObjectId"
      else
        az group deployment create --resource-group $rgName --template-file $file
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

