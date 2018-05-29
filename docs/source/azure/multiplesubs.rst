.. _azure_multiplesubs:

Multiple Subscriptions
======================

If you're using an Azure Service Principal for executing c7n-org
you'll need to ensure that the principal has access to multiple
subscriptions.

For instructions on creating a service principal and granting access
across subscriptions, visit the `Azure authentication docs
page <http://capitalone.github.io/cloud-custodian/docs/azure/authentication.html>`_

**Note**: Currently, running Cloud Custodian on multiple subscriptions
in Azure does not work when running on Windows unless the ``--debug`` flag is set.
It is recommended to run on a Linux or Mac if running against multiple subscriptions.