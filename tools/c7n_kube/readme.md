# Custodian Kubernetes Support

Cloud Custodian can run policies directly inside your cluster, reporting on 
resources that violate those policies, or blocking them altogether.

## Running the server

c7n-kube can be run and installed via poetry. `poetry install && poetry run c7n-kube`.  

| name           | default   | description                                                  |
|----------------|-----------|--------------------------------------------------------------|
| --host         | 127.0.0.1 | (optional) The host that the server should listen on.        |
| --port         | 8800      | (optional) The port the server will listen on.               |
| --policy-dir   |           | Path to the policy directory.                                |
| --on-exception | warn      | Action to take on an internal exception. One of: warn, deny. |
| --cert         |           | Path to the certificate.                                     | 
| --ca-cert      |           | Path to the CA's certificate.                                |
| --cert-key     |           | Path to the certificate's key.                               |

## Generate a MutatingWebhookConfiguration

After the server is running, you'll need to configure and install the 
MutatingWebhookConfiguration manually. To generate a webhook configuration, you
can run `poetry run c7n-kube --generate --endpoint $ENDPOINT_URL --policy-dir $DIR`, and 
it will generate an appropriate configuration for you, based on your policies.

Note: some modification of the webhook configuration may be required. See the 
[documentation](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/) 
on webhooks for more configuration.

## Development

You can use [skaffold](https://github.com/GoogleContainerTools/skaffold/) to 
assist with testing and debugging this controller. Run `skaffold dev` in this
folder to deploy the local container into a local kubernetes cluster. It will 
automatically redeploy it as files change.
