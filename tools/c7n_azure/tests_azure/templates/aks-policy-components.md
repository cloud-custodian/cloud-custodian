# AKS Component Policy States Recording

`aks-policy-components.json` deploys an AKS cluster with the Azure Policy add-on enabled,
plus a resource-group-scoped assignment of the built-in `Microsoft.Kubernetes.Data`
definition "Kubernetes cluster containers should not share host namespaces"
(`47a1ee2f-2a2a-4576-bf2a-e0e36709c2b8`) at `Audit`.

The template itself deploys through `provision.sh` like any other. What it cannot do is
make the cluster non-compliant: a `Microsoft.Kubernetes.Data` definition is evaluated
against the cluster's components, so a recording needs a pod in the cluster that breaks the
rule, and ARM has no way to create one. That part is manual, below.

## Provisioning

```bash
cd tools/c7n_azure/tests_azure/templates && ./provision.sh aks-policy-components && cd -
```

Takes about five minutes, most of it the cluster.

## Making the cluster non-compliant

`kubectl` is not needed locally. `az aks command invoke` runs the command inside the
cluster, which also works when the API server is not reachable from where you are.

```bash
cat > /tmp/bad-hostpid.yaml <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: bad-hostpid
  namespace: default
spec:
  hostPID: true
  containers:
    - name: pause
      image: mcr.microsoft.com/oss/kubernetes/pause:3.6
EOF

az aks command invoke -g test_aks-policy-components -n cctestakspolicy \
    --command "kubectl apply -f bad-hostpid.yaml" --file /tmp/bad-hostpid.yaml
```

The pod must be in a namespace the definition does not exclude. `kube-system`,
`gatekeeper-system`, `azure-arc` and `azure-extensions-usage-system` are excluded by
default, so `default` is the namespace to use.

## Waiting for the verdict

Three things have to happen in order, and none of them can be triggered:

1. the add-on syncs the assignment down as a Gatekeeper constraint,
2. Gatekeeper's audit pod evaluates the cluster, and
3. the result is reported back to Azure Policy.

Poll until the query returns a non-compliant record rather than guessing:

```bash
cluster_id=$(az aks show -g test_aks-policy-components -n cctestakspolicy --query id -o tsv)
az rest --method post --url "https://management.azure.com${cluster_id}/providers/Microsoft.PolicyInsights/componentPolicyStates/latest/queryResults?api-version=2024-10-01" \
    --query "value[].{component:componentId, state:complianceState, definition:policyDefinitionName}" -o table
```

`default/bad-hostpid` showing as `NonCompliant` is what the recorded test asserts on. It
took about 30 minutes from applying the pod on the recording this was written against.

Expect more records than the one assignment accounts for. A component is reported once per
assignment that reaches it, so a subscription running Defender for Cloud reports the same
pod again under `SecurityCenterBuiltIn`, and the recorded test names its own assignment to
keep that out of the result.

## Recording

```bash
rm -f tools/c7n_azure/tests_azure/cassettes/AksPolicyComponentsFilterTest.test_policy_components_matches_non_compliant.json
env -u C7N_FUNCTIONAL -u AZURE_ACCESS_TOKEN .venv/bin/python -m pytest -p no:env -q \
    "tools/c7n_azure/tests_azure/tests_resources/test_aks.py::AksPolicyComponentsFilterTest::test_policy_components_matches_non_compliant"
```

The cassette has to be deleted first; an existing one wins and nothing is re-recorded.
`-p no:env` is required because `test.env` sets `AZURE_ACCESS_TOKEN=fake_token`, which
forces VCR's record mode to `none`.

Two things in a raw recording need a hand afterwards, neither of which
`azure_common.py` covers:

- The `nextLink` continuation token is deflate-compressed base64 and carries the real
  subscription id inside it, where the string substitution cannot reach. Nothing parses
  it, so replace the token in the `nextLink` and in the request that follows it.
- The cluster's managed identity `principalId`, the `clientId`/`objectId` of its
  `azurepolicy` and `agentpool` identities, the generated public IP name and the cluster's
  DNS label are all real ids. Rename them, keeping the entries.

The pods `az aks command invoke` leaves behind are reported as components too. They are
not part of the fixture and carry a per-run id, so drop those records and correct
`@odata.count` to match.

Then replay it the way CI does, with the plugin back on:

```bash
.venv/bin/python -m pytest -q \
    "tools/c7n_azure/tests_azure/tests_resources/test_aks.py::AksPolicyComponentsFilterTest"
```

## Cleanup

```bash
cd tools/c7n_azure/tests_azure/templates && ./cleanup.sh aks-policy-components && cd -
```

The policy assignment is scoped to the resource group, so deleting the group removes it
along with the cluster. Nothing is left behind at subscription scope.
