.. _azure_multiplesubs:

Multiple Subscriptions
======================

See 
`C7N-Org Readme <https://github.com/capitalone/cloud-custodian/tree/master/tools/c7n_org>`_ 
for general information on running Cloud Custodian across accounts and subscriptions.

If you're using an Azure Service Principal for executing c7n-org
you'll need to ensure that the principal has access to multiple
subscriptions. For instructions on creating a service principal and granting access
across subscriptions, visit the `Azure authentication docs
page <http://capitalone.github.io/cloud-custodian/docs/azure/authentication.html>`_

**Note**: There are pending issues with running C7N-Org on Windows. It may be required to 
use the ``--debug`` flag when running on Windows. 
