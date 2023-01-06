# Getting Started

## Install Cloud Custodian

These instructions will install Cloud Custodian. Cloud Custodian is a Python
application that supports Python 3 on Linux, MacOS and Windows. We recommend
using at least the minimum supported version of Python.

If `python3 --version` shows a Python version that is not [actively
supported](https://devguide.python.org/versions/#versions) and the
steps above don't apply to your environment, you can still install a current
release of Python manually. [This guide](https://realpython.com/installing-python/) may be a useful reference.

!!! note

    Some Enterprise/Long Term Support Linux distributions may support Python
    longer than the upstream support period. If you are in this situation it might be prudent to contact your vendor to see if there are other supported ways to use a more recent version. In some cases using the Docker container might be an appropriate solution.

=== "Linux and OSX"

    To install Cloud Custodian :

        python3 -m venv custodian
        source custodian/bin/activate
        pip install c7n       # This includes AWS support

    To install Cloud Custodian for Azure, you will also need to run:

        pip install c7n_azure # Install Azure package

    To install Cloud Custodian for GCP, you will also need to run:

        pip install c7n_gcp   # Install GCP Package


=== "Windows" 
    
    To install Cloud Custodian run:

        python3 -m venv custodian
        ./custodian/bin/activate
        pip install c7n    # This includes AWS support

    To install Cloud Custodian for Azure, you will also need to run:

        pip install c7n_azure

    To install Cloud Custodian for GCP, you will also need to run:

        pip install c7n_gcp

=== "Docker"

    To install via docker, run:

        docker pull cloudcustodian/c7n

    You'll need to export cloud provider credentials to the container when
    executing. One example, if you\'re using environment variables for
    provider credentials:

        docker run -it \
          -v $(pwd)/output:/home/custodian/output \
          -v $(pwd)/policy.yml:/home/custodian/policy.yml \
          --env-file <(env | grep "^AWS\|^AZURE\|^GOOGLE") \
             cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml

=== "Kubernetes"

    We provide a helm chart, you need to get the repo added to helm!

    ```sh
    helm repo add c7n https://cloud-custodian.github.io/helm-charts/
    helm repo update
    helm search repo c7n -l
    ```

    From there you can setup a `values.yml` file and install it.  A good starting
    point is this:

    ```yaml
    certManager:
      enabled: true

    policies:
      source: configMap
      configMap:
        policies:
          - name: missing-recommended-labels
            mode:
              type: k8s-admission
              on-match: deny
              operations:
                - CREATE
                - UPDATE
            description: |
              Kubernetes recommmended the following labels from its docs:
              app.kubernetes.io/name
              app.kubernetes.io/instance
              app.kubernetes.io/version
              app.kubernetes.io/component
              app.kubernetes.io/part-of
              app.kubernetes.io/managed-by
              https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/
            resource: k8s.pod
            filters:
              - or:
                  - metadata.labels."app.kubernetes.io/name": absent
                  - metadata.labels."app.kubernetes.io/instance": absent
                  - metadata.labels."app.kubernetes.io/version": absent
                  - metadata.labels."app.kubernetes.io/component": absent
                  - metadata.labels."app.kubernetes.io/part-of": absent
                  - metadata.labels."app.kubernetes.io/managed-by": absent

    webhook:
      caBundle: will-be-replaced-by-cert-manager

      rules:
        - apiGroups: [""]
          apiVersions: ["v1"]
          operations: ["CREATE"]
          resources: ["pods"]
          scope: Namespaced
    ```

    This will provide you with your first policy that enforces best practice labeling
    on your pods. Then you can install the chart!

    ```sh
    helm install c7n-kube c7n/c7n-kube  --namespace c7n-system -f values.yml --create-namespace
    ```
    See the [Kubernetes section](https://cloudcustodian.io/docs/kubernetes/gettingstarted.html)
    of the documentation for more information. 

!!! note 

    Ensure you install the correct follow-on package depending on the cloud
    you are deploying to, otherwise you won't have the right modules for that
    specific cloud.

## Explore Cloud Custodian

Run `custodian -h` to see a list of available commands.

Run `custodian schema` to see the complete list of cloud resources against
which you can run policies. To invoke command-line help with more information
about policy schema details, run `custodian schema -h`.

Run `custodian schema <cloud-provider>` to see the available resources for a
specific cloud provider: `custodian schema aws`

Run `custodian schema <cloud-provider>.<resource>` to see the available
filters and actions for each resource.

Drill down to get more information about available policy settings for each
resource, where the model for the command is::

    custodian schema <cloud>.<resource>.<category>.<item>

For example:

    custodian schema aws.s3.filters.is-log-target

provides the following information::

```
  Help
  ----

  Filter and return buckets are log destinations.

  Not suitable for use in lambda on large accounts, This is a api
  heavy process to detect scan all possible log sources.

  Sources:
    - elb (Access Log)
    - s3 (Access Log)
    - cfn (Template writes)
    - cloudtrail

  :example:

      .. code-block: yaml

          policies:
            - name: s3-log-bucket
              resource: s3
              filters:
                - type: is-log-target

  Schema
  ------

  {   'additionalProperties': False,
      'properties': {   'type': {   'enum': ['is-log-target']},
                        'value': {   'type': 'boolean'}},
      'required': ['type'],
      'type': 'object'}
```

Additionally, you can use the schema command to view information on the different
supported modes in Cloud Custodian::

    custodian schema mode

## Cloud Provider Specific Help

For specific setup isntructions for AWS, Azure, and GCP, visit the relevant getting started
page.

- [AWS](https://cloudcustodian.io/docs/aws/gettingstarted.html)
- [Azure](https://cloudcustodian.io/docs/azure/gettingstarted.html)
- [GCP](https://cloudcustodian.io/docs/gcp/gettingstarted.html)

## Troubleshooting & Tinkering

The policy is validated automatically when you run it, but you can also
validate it separately:

    custodian validate custodian.yml

You can also check which resources are identified by the policy, without
running any actions on the resources:

    custodian run --dryrun -s . custodian.yml

### Monitor resources

Additional commands let you monitor your services in detail.

You can generate metrics, log outputs, and output to blob storage in each of the different providers (AWS, Azure, Google Cloud Platform). See the [cloud provider specific help](#cloud-provider-specific-help) at the top of this section for more information.

### Editor Integration

If your preferred editor supports language servers, you can configure
it to provide completion and validation while authoring policies.

First generate use custodian to generate a json schema file::

    custodian schema --json > schema.json

Next install a YAML plug-in for your editor, like [YAML for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) or
[coc-yaml for coc.nvim](https://github.com/neoclide/coc-yaml). Both plug-ins
use the [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) under the hood.

You'll then need to configure your plug-in to use the generated `schema.json`
as the schema for your policy files. For example in Visual Studio Code,
navigate to the settings for the YAML plug-in and under Schemas, edit
configuration file and add the following schema configuration::

      "yaml.schemas": {
        "./schema.json": "*yml"
      },

Note the path to schema.json can either be either relative or the full path.

You'll now have completion and validation while authoring policies.

![](c7n-editor.png)

Note if you're authoring policies in json you can also configure the
json-language-server for the same.

Also, if you're seeing errors like ``'Request textDocument/hover failed with
message: Cannot read property '$ref' of null'`` try re-creating your
schema.json file.

### Tab Completion

To enable command-line tab completion for `custodian` on bash do the following
one-time steps:

Run:

    activate-global-python-argcomplete

Now launch a new shell (or refresh your bash environment by sourcing the appropriate file).

### Troubleshooting

If you get an error about "complete -D" not being supported, you need to update bash.
See the "Base Version Compatability" note `in the [argcomplete docs](https://argcomplete.readthedocs.io/en/latest/#global-completion).

If you have other errors, or for tcsh support, see [the argcomplete docs](https://argcomplete.readthedocs.io/en/latest/#activating-global-completion).

If you are invoking `custodian` via the `python` executable tab completion will not work.
You must invoke `custodian` directly.
