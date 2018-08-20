.. _azure_authentication:

Authentication
==============

The plugin supports three distinct authentication types, including Azure CLI integration, service principal,
and raw tokens.


Service Principal
-----------------

Service principal must be provided via environment variables.

You can create a service principal with Azure CLI as follows:

.. code-block:: bash

    # select correct subscription
    az account set -s "my subscription name"

    # create service principal
    az ad sp create-for-rbac --name <name> --password <password>

This will yield something like:

.. code-block:: javascript

    {
      "appId": appid,
      "displayName": name,
      "name": name,
      "password": password,
      "tenant": guid
    }

You will need to map it to environment variables for Custodian like this:

.. code-block:: bash

    AZURE_TENANT_ID=tenant
    AZURE_SUBSCRIPTION_ID=subscriptionId
    AZURE_CLIENT_ID=appId
    AZURE_CLIENT_SECRET=password


If you're using a Service Principal across subscriptions with `c7n-org` you'll
need to grant it access to each of the subscriptions.

Once the service principal is created, follow these steps:

- Open the `Subscriptions` tab
- Select a subscription you'd like to manage with Cloud Custodian
- Click `Access Control (IAM)`
- Click `Add`
- Set Role to `Contributor`
- Type name of service principal in search bar and select it
- Click `Save`


Access Token
------------

Passing access tokens directly is useful for integration or fake test authentication.

For fake test authentication environment variables should be configured as shown below:

.. code-block:: bash

    AZURE_ACCESS_TOKEN=fake_token
    AZURE_SUBSCRIPTION_ID=ea42f556-5106-4743-99b0-c129bfa71a47

You will also find this configuration in tox.ini.
