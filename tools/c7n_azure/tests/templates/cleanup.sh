#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

# Delete RG's for each template file
for file in "$templateDirectory"/*.json; do
  fileName=${file##*/}
  filenameNoExtension=${fileName%.*}
  rgName="test_$filenameNoExtension"

  if [ $# -eq 0 ] || [[ "$@" =~ "$filenameNoExtension" ]]; then
    echo "Deleting $rgName"
    az group delete --name $rgName --yes --no-wait
  else
    echo "Skipping $rgName"
  fi

done

# Destroy ACS resource
rgName=test_containerservice
if [ $# -eq 0 ] || [[ "$@" =~ "containerservice" ]]; then
  az group delete --name $rgName --yes --no-wait
else
  echo "Skipping $rgName"
fi

# Destroy Azure Policy Assignment
if [ $# -eq 0 ] || [[ "$@" =~ "policyassignment" ]]; then
  az policy assignment delete --name cctestpolicy --no-wait
else
  echo "Skipping policyassignment"
fi