#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

# If `az ad signed-in-user show` fails then update your Azure CLI version

# If you can't provision keyvault or cost-management-export resources please ensure you use
# your user account and not a Service Principals.
# cost-management-export: requires SP to have valid email claim
# keyvault: Managed Storage can't be provisioned with SP

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"
SUB_ID=$(az account show --query id --output tsv)

print_failed_group_deployment() {
    rgName="$1"
    latest_deployment=$(az deployment group list \
        --resource-group "$rgName" \
        --query "[0].name" \
        --output tsv 2>/dev/null)
    if [[ -n "$latest_deployment" ]]; then
        echo "Last deployment '$latest_deployment' operations for resource group '$rgName':"
        az deployment group operation list \
            --resource-group "$rgName" \
            --name "$latest_deployment" \
            --query "[].{state:properties.provisioningState,status:properties.statusMessage}" \
            --output jsonc \
            || az group deployment operation list \
                --resource-group "$rgName" \
                --name "$latest_deployment" \
                --query "[].{state:properties.provisioningState,status:properties.statusMessage}" \
                --output jsonc \
            || az deployment group show \
                --resource-group "$rgName" \
                --name "$latest_deployment" \
                --query "{state:properties.provisioningState,error:properties.error}" \
                --output jsonc \
            || true
    fi
}

if [[ $(az account show --query user.type --out tsv) == "user" ]]; then
    is_user=1
else
    is_user=0
fi

if [[ $# -eq 0 ]]; then
    # If there is no arguments -- deploy everything
    deploy_all=1
else
    if [[ $1 == "--skip" ]]; then
        # If we see option '--skip' -- deploy everything except for specific templates
        deploy_all=1
        skip_list="${@:2}"
    else
        # If there is no '--skip', deploy specific templates
        deploy_all=0
        deploy_list="${@:1}"
    fi
fi

# Append uniqueId parameter if template has "uniqueId" parameter defined to avoid conflicts with already 
# existing resources in case of multiple deployments
append_generated_unique_id_parameter() {
    local template_file="$1"
    local -n params_ref="$2"

    if grep -q '"uniqueId"[[:space:]]*:' "$template_file"; then
        local unique_suffix
        unique_suffix="$(date +%s%N | tail -c 13)"
        params_ref+=("uniqueId=${unique_suffix}")
    fi
}

ensure_active_principal_object_id() {
    if [[ -n "$ASSIGNEE_OBJECT_ID" ]]; then
        return 0
    fi

    if [[ ${is_user} -eq 1 ]]; then
        ASSIGNEE_OBJECT_ID=$(az ad signed-in-user show --query id --output tsv 2>/dev/null)
        if [[ -n "$ASSIGNEE_OBJECT_ID" ]]; then
            return 0
        fi
    fi

    echo "Unable to resolve ASSIGNEE_OBJECT_ID for role assignment."
    echo "Set ASSIGNEE_OBJECT_ID environment variable and retry."
    return 1
}

ensure_role_for_active_principal() {
    local resource_group_name="$1"
    local role_name="$2"
    local principal_type="${3:-User}"
    local scope="/subscriptions/${SUB_ID}/resourceGroups/${resource_group_name}"

    if [[ -z "$resource_group_name" ]] || [[ -z "$role_name" ]]; then
        echo "ensure_role_for_active_principal requires: <resource_group_name> <role_name> [principal_type]"
        return 1
    fi

    ensure_active_principal_object_id || return 1
    echo "Ensuring role '${role_name}' for principal '${ASSIGNEE_OBJECT_ID}' on scope '${scope}'"

    existing_count=$(az role assignment list \
        --scope "$scope" \
        --assignee-object-id "$ASSIGNEE_OBJECT_ID" \
        --role "$role_name" \
        --query "length(@)" \
        --output tsv 2>/dev/null)

    if [[ "$existing_count" == "0" ]] || [[ -z "$existing_count" ]]; then
        echo "Assigning role '$role_name' to '$ASSIGNEE_OBJECT_ID' on '$scope'"
        az role assignment create \
            --assignee-object-id "$ASSIGNEE_OBJECT_ID" \
            --assignee-principal-type "$principal_type" \
            --role "$role_name" \
            --scope "$scope" \
            --output None
    else
        echo "Role '$role_name' already assigned for assignee '$ASSIGNEE_OBJECT_ID' on scope '$scope'"
    fi

    # Propagation check: wait until ARM role assignment query returns the assignment.
    for attempt in 1 2 3 4 5 6; do
        existing_count=$(az role assignment list \
            --scope "$scope" \
            --assignee-object-id "$ASSIGNEE_OBJECT_ID" \
            --role "$role_name" \
            --query "length(@)" \
            --output tsv 2>/dev/null)

        if [[ "$existing_count" != "0" ]] && [[ -n "$existing_count" ]]; then
            return 0
        fi

        echo "Waiting for role assignment propagation (attempt ${attempt}/6) ..."
        sleep 10
    done

    echo "Role assignment did not appear after propagation checks."
    return 1
}

deploy_resource() {
    echo "Deployment for ${filenameNoExtension} started"

    fileName=${1##*/}
    filenameNoExtension=${fileName%.*}
    rgName="test_$filenameNoExtension"

    az group create --name $rgName --location $resourceLocation --output None

    if [[ "$fileName" == "keyvault.json" ]]; then

        if [[ ${is_user} -ne 1 ]]; then
            echo "KeyVault can't be provisioned with Service Principal due to Keyvault Managed Storage Account restrictions"
            exit 1
        fi

        azureAdUserObjectId=$(az ad signed-in-user show --query id --output tsv)
        az deployment group create --resource-group $rgName --template-file $file \
            --parameters "userObjectId=$azureAdUserObjectId" --output None

        vault_name=$(az keyvault list --resource-group $rgName --query [0].name --output tsv)

        storage_id=$(az storage account list --resource-group ${rgName} --query [0].id --output tsv)

        az keyvault key create --vault-name ${vault_name} --name cctestrsa --kty RSA --output None
        az keyvault key create --vault-name ${vault_name} --name cctestec --kty EC --output None

        az keyvault certificate create --vault-name ${vault_name} --name cctest1 -p "$(az keyvault certificate get-default-policy)" --output None
        az keyvault certificate create --vault-name ${vault_name} --name cctest2 -p "$(az keyvault certificate get-default-policy)" --output None

     #   az role assignment create --role "Storage Account Key Operator Service Role" --assignee cfa8b339-82a2-471a-a3c9-0fc0be7a4093 --scope ${storage_id} --output None
        az keyvault storage add --vault-name ${vault_name} -n storage1 --active-key-name key1 --resource-id ${storage_id} --auto-regenerate-key True --regeneration-period P720D  --output None
        az keyvault storage add --vault-name ${vault_name} -n storage2 --active-key-name key2 --resource-id ${storage_id} --auto-regenerate-key False --output None

    elif [[ "$fileName" == "aks.json" ]]; then

        az deployment group create --resource-group $rgName --template-file $file --parameters client_id=$AZURE_CLIENT_ID client_secret=$AZURE_CLIENT_SECRET --mode Complete --output None

    elif [[ "$fileName" == "cost-management-export.json" ]]; then

        if [[ ${is_user} -ne 1 ]]; then
            echo "Cost Management Export can't be provisioned with Service Principal due to Keyvault Managed Storage Account restrictions"
            exit 1
        fi

        # Deploy storage account required for the export
        az deployment group create --resource-group $rgName --template-file $file --mode Complete --output None

        token=$(az account get-access-token --query accessToken --output tsv)
        storage_id=$(az storage account list --resource-group $rgName --query [0].id --output tsv)
        subscription_id=$(az account show --query id --output tsv)
        url=https://management.azure.com/subscriptions/${subscription_id}/providers/Microsoft.CostManagement/exports/cccostexport?api-version=2019-01-01

        eval "echo \"$(cat cost-management-export-body.template)\"" > cost-management.body

        curl -X PUT -d "@cost-management.body" -H "content-type: application/json" -H "Authorization: Bearer ${token}" ${url}

        rm -f cost-management.body

    elif [[ "$fileName" == "ai-foundry-application.json" ]]; then

        unique_suffix="$(date +%s%N | tail -c 13)"

        account_name="cctestaifoundry${unique_suffix}"
        project_name="${AZURE_AI_FOUNDRY_PROJECT_NAME:-cctest-${filenameNoExtension}-project}"
        deployment_name="${AZURE_OPENAI_DEPLOYMENT_NAME:-cctest-gpt4o-mini}"
        model_name="${AZURE_OPENAI_MODEL_NAME:-gpt-4o-mini}"
        model_version="${AZURE_OPENAI_MODEL_VERSION:-2024-07-18}"
        app_name="cctest-aifoundry-application"
        phase1_deployment_name="ai-foundry-application-phase1-${unique_suffix}"
        phase2_deployment_name="ai-foundry-application-phase2-${unique_suffix}"

        # Phase 1: deploy account + project + model deployment (no application yet).
        az deployment group create \
            --name "$phase1_deployment_name" \
            --resource-group "$rgName" \
            --template-file "$file" \
            --parameters "uniqueId=${unique_suffix}" \
                         "deploymentName=${deployment_name}" \
                         "modelName=${model_name}" \
                         "modelVersion=${model_version}" \
                         "projectName=${project_name}" \
                         "deployApplication=false" \
            --mode Incremental \
            --output None

        # Ensure data-plane role for real agent creation.
        principal_type="ServicePrincipal"
        if [[ ${is_user} -eq 1 ]]; then
            principal_type="User"
        fi
        if ! ensure_role_for_active_principal "$rgName" "Azure AI User" "$principal_type"; then
            echo "Required role assignment check failed; cannot continue with agent creation."
            exit 1
        fi

        # Phase 2: create a modern Foundry agent (no legacy assistants endpoint, no existence checks).
        project_endpoint="https://${account_name}.services.ai.azure.com/api/projects/${project_name}"
        generated_agent_name="cctest-aifoundry-agent-${unique_suffix}"
        export PROJECT_ENDPOINT="${project_endpoint}"
        export MODEL_DEPLOYMENT_NAME="${deployment_name}"
        export GENERATED_AGENT_NAME="${generated_agent_name}"
        export GENERATED_AGENT_INSTRUCTIONS="Fixture agent for Cloud Custodian AI Foundry application tests."

        if ! agent_json=$(python3 - <<'PY'
import json
import os
import sys

try:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects.models import PromptAgentDefinition, AgentKind
except Exception as e:
    print(f"Missing dependency for modern Foundry agent creation: {e}", file=sys.stderr)
    print("Install: pip install azure-ai-projects azure-identity", file=sys.stderr)
    sys.exit(1)

endpoint = os.environ["PROJECT_ENDPOINT"]
deployment_name = os.environ["MODEL_DEPLOYMENT_NAME"]
agent_name = os.environ["GENERATED_AGENT_NAME"]
instructions = os.environ["GENERATED_AGENT_INSTRUCTIONS"]

credential = DefaultAzureCredential()
client = AIProjectClient(endpoint=endpoint, credential=credential)
with client:
    agents_ops = client.agents
    if hasattr(agents_ops, "create_version") and hasattr(agents_ops, "get"):
        definition = PromptAgentDefinition(
            kind=AgentKind.PROMPT,
            model=deployment_name,
            instructions=instructions
        )
        # Create a new modern agent version and then resolve stable agent details.
        agents_ops.create_version(
            agent_name=agent_name,
            definition=definition,
            description="Fixture agent for Cloud Custodian AI Foundry application tests."
        )
        agent = agents_ops.get(agent_name=agent_name)
    elif hasattr(agents_ops, "create_agent"):
        # Compatibility with older/newer SDK shapes that expose create_agent directly.
        agent = agents_ops.create_agent(
            model=deployment_name,
            name=agent_name,
            instructions=instructions
        )
    elif hasattr(agents_ops, "create"):
        # Compatibility with SDK shapes that expose create directly.
        agent = agents_ops.create(
            model=deployment_name,
            name=agent_name,
            instructions=instructions
        )
    else:
        methods = [m for m in dir(agents_ops) if not m.startswith("_")]
        print(
            "Unable to create Foundry agent: AgentsOperations has neither "
            "'create_agent' nor 'create'. Available methods: "
            f"{methods}",
            file=sys.stderr
        )
        sys.exit(1)

if isinstance(agent, dict):
    agent_id = agent.get("id", "")
    agent_name_out = agent.get("name", "")
else:
    agent_id = getattr(agent, "id", "")
    agent_name_out = getattr(agent, "name", "")

print(json.dumps({"agentId": agent_id, "agentName": agent_name_out}))
PY
        ); then
            echo "Modern Foundry agent creation failed."
            exit 1
        fi

        agent_id=$(echo "${agent_json}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('agentId',''))")
        agent_name=$(echo "${agent_json}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('agentName',''))")
        if [[ -z "${agent_id}" ]] || [[ -z "${agent_name}" ]]; then
            echo "Modern Foundry agent creation returned empty id/name."
            echo "Raw response: ${agent_json}"
            exit 1
        fi

        # Phase 3: deploy application with real agent reference (retry on transient backend errors).
        app_deploy_ok=0
        for attempt in 1 2 3 4 5 6; do
            phase2_attempt_name="${phase2_deployment_name}-attempt${attempt}"
            deploy_err=""
            if deploy_err=$(az deployment group create \
                --name "$phase2_attempt_name" \
                --resource-group "$rgName" \
                --template-file "$file" \
                --parameters "uniqueId=${unique_suffix}" \
                             "deploymentName=${deployment_name}" \
                             "modelName=${model_name}" \
                             "modelVersion=${model_version}" \
                             "projectName=${project_name}" \
                             "deployApplication=true" \
                             "agentId=${agent_id}" \
                             "agentName=${agent_name}" \
                --mode Incremental \
                --output None 2>&1); then
                app_deploy_ok=1
                break
            fi

            # RBAC/data-plane propagation errors: retry.
            if echo "${deploy_err}" | grep -Eq \
                "Microsoft\\.CognitiveServices/accounts/AIServices/agents/write|Principal does not have access to API/Operation|PermissionDenied"; then
                echo "Application deployment hit permission/propagation issue (attempt ${attempt}/6); waiting before retry..."
                sleep 30
                continue
            fi

            # Backend not-ready race: retry.
            if echo "${deploy_err}" | grep -Eq "ApplicationNotFound|NotFound"; then
                echo "Application deployment not ready yet (attempt ${attempt}/6); waiting before retry..."
                sleep 30
                continue
            fi

            # SystemError is treated as hard failure for this run.
            if echo "${deploy_err}" | grep -Eq "Message:[[:space:]]*SystemError|\"code\":\"SystemError\"|code.:.SystemError|\\(SystemError\\)"; then
                echo "Application deployment failed with SystemError on attempt ${attempt}; stopping retries."
                echo "${deploy_err}"
                exit 1
            fi

            echo "Application deployment failed:"
            echo "${deploy_err}"
            exit 1
        done
        if [[ "$app_deploy_ok" != "1" ]]; then
            echo "Application deployment failed after retries."
            exit 1
        fi

    else
        template_parameters=()
        append_generated_unique_id_parameter "$file" template_parameters

        if [[ ${#template_parameters[@]} -gt 0 ]]; then
            az deployment group create \
                --resource-group "$rgName" \
                --template-file "$file" \
                --parameters "${template_parameters[@]}" \
                --mode Complete \
                --output None
        else
            az deployment group create --resource-group $rgName --template-file $file --mode Complete --output None
        fi
    fi

    if [[ "$fileName" == "cosmosdb.json" ]]; then
        ip=$(curl -s https://checkip.amazonaws.com)
        allow_list="$ip,104.42.195.92,40.76.54.131,52.176.6.30,52.169.50.45,52.187.184.26"
        sub_id=$(az account show --query id --output tsv)
        suffix="${sub_id:${#sub_id} - 12}"
        echo "Adding local external IP (${ip}) and azure portals to cosmos firewall allow list..."
        az cosmosdb update -g $rgName -n cctestcosmosdb$suffix --ip-range-filter $allow_list
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

function should_deploy() {
    if [[ ${deploy_all} -eq 1 ]]; then
        if ! [[ "${skip_list[@]}" =~ $1 ]]; then
            return 1
        fi
    else
        if [[ "${deploy_list[@]}" =~ $1 ]]; then
            return 1
        fi
    fi
    return 0
}

# Ensure AZURE_CLIENT_ID and AZURE_CLIENT_SECRET are available for AKS deployment
should_deploy "aks"
if [[ $? -eq 1 ]]; then
    if [[ -z "$AZURE_CLIENT_ID" ]] || [[ -z "$AZURE_CLIENT_SECRET" ]]; then
        echo "AZURE_CLIENT_ID AND AZURE_CLIENT_SECRET environment variables are required to deploy AKS"
        exit 1
    fi
fi

# Create resource groups and deploy for each template file
for file in "$templateDirectory"/*.json; do
    fileName=${file##*/}
    filenameNoExtension=${fileName%.*}
    should_deploy "$filenameNoExtension"
    if [[ $? -eq 1 ]]; then
        deploy_resource ${file} &
    fi
done

# Provision non-arm resources
should_deploy "containerservice"
if [[ $? -eq 1 ]]; then
    deploy_acs &
fi

should_deploy "policy"
if [[ $? -eq 1 ]]; then
    deploy_policy_assignment &
fi

# Wait until all deployments are finished
wait
