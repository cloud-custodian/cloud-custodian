
# Cloud Custodian - Azure Support

This a plugin to Cloud Custodian that adds Azure support.

## Install Cloud Custodian and Azure Plugin

The Azure provider must be installed as a separate package in addition to c7n.

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ virtualenv custodian
    $ source custodian/bin/activate
    (custodian) $ pip install -e cloud-custodian/.
    (custodian) $ pip install -e cloud-custodian/tools/c7n_azure/.


## Write your first policy

A policy specifies the following items:

- The type of resource to run the policy against
- Filters to narrow down the set of resources
- Actions to take on the filtered set of resources

For this tutorial we will add a tag to all virtual machines with the name "Hello" and the value "World".

Create a file named ``custodian.yml`` with this content:

    policies:
        - name: my-first-policy
          description: |
            Adds a tag to all virtual machines
          resource: azure.vm
          actions:
            - type: tag
              tag: Hello
              value: World

## Run your policy

First, choose one of the supported authentication mechanisms and either log in to Azure CLI or set
environment variables as documented in [Authentication](https://cloudcustodian.io/docs/azure/authentication.html#azure-authentication).

    custodian run --output-dir=. custodian.yml


If successful, you should see output similar to the following on the command line

    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: azure.vm
    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:azure.vm has count:1 time:1.38
    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: tag: 1 execution_time: 0.67


You should also find a new ``my-first-policy`` directory with a log and other
files (subsequent runs will append to the log by default rather than
overwriting it).

## Links
- [Getting Started](https://cloudcustodian.io/docs/azure/gettingstarted.html)
- [Example Scenarios](https://cloudcustodian.io/docs/azure/examples/index.html)
- [Example Policies](https://cloudcustodian.io/docs/azure/policy/index.html)


## Running Tests

If you'd like to help with the development of Azure support, you'll need
[uv](https://docs.astral.sh/uv/) installed. It provides a pip-compatible
interface, & will handle all the dependencies needed for you.

You can then run the unit tests like this:

```shell
# Assuming you're in the `cloud-custodian` top-level directory...
$ cd tools/c7n_azure

$ uv run pytest tests_azure
```
