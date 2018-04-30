Service Principal Authentication
--------------------------------

To authenticate via environment variables, you can create a service principal with Azure CLI

```
# select correct subscription
az account set -s "my subscription name"

# create service principal
az ad sp create-for-rbac --name <name> --password <password>
```
This will yield something like:

```
{
  "appId": appid,
  "displayName": name,
  "name": name,
  "password": password,
  "tenant": guid
}
```
You will need to map it to environment variables like this:

AZURE_TENANT_ID=tenant
AZURE_SUBSCRIPTION_ID=subscription id
AZURE_CLIENT_ID=appId
AZURE_CLIENT_SECRET=password



Azure CLI Authentication
------------------------

Set environment variable `AZURE_CLI_AUTH` to any value, and session will pull credentials from cached AZ Login and
default subscription.



Fake Authentication
-------------------

Fake authentication for tests should be configured as seen in tox.ini, basically:

```
AZURE_ACCESS_TOKEN=fake_token
AZURE_SUBSCRIPTION_ID=ea42f556-5106-4743-99b0-c129bfa71a47
```