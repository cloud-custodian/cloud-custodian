#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

delete_resource() {
    echo "Delete for $filenameNoExtension started"
    fileName=${1##*/}
    filenameNoExtension=${fileName%.*}
    rgName="test_$filenameNoExtension"
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

# Delete RG's for each template file
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}

    if [ $# -eq 0 ] || [[ "$@" =~ "$filenameNoExtension" ]]; then
        delete_resource ${file} &
    fi
done

# Destroy ACS resource
if [ $# -eq 0 ] || [[ "$@" =~ "containerservice" ]]; then
    delete_acs &
fi

# Destroy Azure Policy Assignment
if [ $# -eq 0 ] || [[ "$@" =~ "policyassignment" ]]; then
    delete_policy_assignment &
fi

# Wait until all cleanup is finished
wait