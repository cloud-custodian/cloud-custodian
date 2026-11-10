#!/bin/bash
set -euo pipefail

resource_group="test_machine-learning-compute-cluster"
cluster_name="cctest-ml-cluster"
current_job="cctest-current-standalone"
recent_job="cctest-recent-standalone"
pipeline_job="cctest-recent-pipeline"

workspace_name() {
    az ml workspace list \
        --resource-group "$resource_group" \
        --query '[0].name' \
        --output tsv
}

archive_experiment() {
    local experiment_name="$1"
    local subscription_id
    local discovery_url
    local history_url
    local experiment_id
    subscription_id=$(az account show --query id --output tsv)
    discovery_url=$(az ml workspace show \
        --resource-group "$resource_group" \
        --name "$workspace" \
        --query discovery_url \
        --output tsv)
    history_url="${discovery_url%/discovery}/history/v1.0/subscriptions"
    history_url+="/$subscription_id/resourceGroups/$resource_group"
    history_url+="/providers/Microsoft.MachineLearningServices"
    history_url+="/workspaces/$workspace"
    experiment_id=$(az rest \
        --method get \
        --resource https://ml.azure.com \
        --url "$history_url/experiments/$experiment_name?api-version=2023-10-01" \
        --query experimentId \
        --output tsv)
    az rest \
        --method patch \
        --resource https://ml.azure.com \
        --url "$history_url/experimentids/$experiment_id?api-version=2023-10-01" \
        --body '{"archive": true}' \
        --output none
}

job_status() {
    az ml job show \
        --resource-group "$resource_group" \
        --workspace-name "$workspace" \
        --name "$1" \
        --query status \
        --output tsv
}

wait_for_status() {
    local job_name="$1"
    shift
    local status
    for _ in {1..180}; do
        status=$(job_status "$job_name")
        for expected in "$@"; do
            if [[ "$status" == "$expected" ]]; then
                echo "$job_name reached $status"
                return 0
            fi
        done
        if [[ "$status" =~ ^(Failed|Canceled|NotResponding)$ ]]; then
            echo "$job_name unexpectedly reached $status" >&2
            return 1
        fi
        sleep 5
    done
    echo "Timed out waiting for $job_name; last status was $status" >&2
    return 1
}

wait_for_zero_running_nodes() {
    local compute_url
    local running_nodes
    compute_url="https://management.azure.com/subscriptions/{subscriptionId}"
    compute_url+="/resourceGroups/$resource_group"
    compute_url+="/providers/Microsoft.MachineLearningServices"
    compute_url+="/workspaces/$workspace/computes/$cluster_name"
    compute_url+="?api-version=2023-04-01"
    for _ in {1..90}; do
        running_nodes=$(az rest \
            --method get \
            --url "$compute_url" \
            --query properties.properties.nodeStateCounts.runningNodeCount \
            --output tsv)
        if [[ "$running_nodes" == "0" ]]; then
            echo "$cluster_name reached zero running nodes"
            return 0
        fi
        sleep 10
    done
    echo "$cluster_name did not reach zero running nodes" >&2
    return 1
}

create_current_job() {
    cat >"$temp_directory/current.yml" <<EOF
\$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
type: command
name: $current_job
experiment_name: cctest-current
compute: azureml:$cluster_name
command: sleep 1800
environment:
  image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04
EOF
    az ml job create \
        --resource-group "$resource_group" \
        --workspace-name "$workspace" \
        --file "$temp_directory/current.yml" \
        --output none
    wait_for_status \
        "$current_job" \
        NotStarted Starting Provisioning Preparing Queued Running
}

create_recent_jobs() {
    cat >"$temp_directory/recent.yml" <<EOF
\$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
type: command
name: $recent_job
experiment_name: cctest-recent-archived
compute: azureml:$cluster_name
command: echo recent-standalone
environment:
  image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04
EOF
    cat >"$temp_directory/pipeline.yml" <<EOF
\$schema: https://azuremlschemas.azureedge.net/latest/pipelineJob.schema.json
type: pipeline
name: $pipeline_job
experiment_name: cctest-recent-active
settings:
  default_compute: azureml:$cluster_name
jobs:
  child:
    type: command
    command: echo recent-pipeline-child
    environment:
      image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04
EOF
    az ml job create \
        --resource-group "$resource_group" \
        --workspace-name "$workspace" \
        --file "$temp_directory/recent.yml" \
        --output none
    az ml job create \
        --resource-group "$resource_group" \
        --workspace-name "$workspace" \
        --file "$temp_directory/pipeline.yml" \
        --output none
    wait_for_status "$recent_job" Completed
    wait_for_status "$pipeline_job" Completed
    archive_experiment cctest-recent-archived
    wait_for_zero_running_nodes
}

cancel_job() {
    local job_name="$1"
    local status
    status=$(job_status "$job_name" 2>/dev/null || true)
    if [[ "$status" =~ ^(NotStarted|Starting|Provisioning|Preparing|Queued|Running|Finalizing)$ ]]; then
        az ml job cancel \
            --resource-group "$resource_group" \
            --workspace-name "$workspace" \
            --name "$job_name" \
            --output none
    fi
}

usage() {
    echo "Usage: $0 recent|current|cleanup" >&2
    exit 2
}

[[ $# -eq 1 ]] || usage
workspace=$(workspace_name)
[[ -n "$workspace" ]] || {
    echo "No workspace exists in $resource_group" >&2
    exit 1
}
temp_directory=$(mktemp -d)
trap 'rm -rf "$temp_directory"' EXIT

case "$1" in
    recent)
        create_recent_jobs
        ;;
    current)
        create_current_job
        ;;
    cleanup)
        cancel_job "$current_job"
        cancel_job "$recent_job"
        cancel_job "$pipeline_job"
        ;;
    *)
        usage
        ;;
esac
