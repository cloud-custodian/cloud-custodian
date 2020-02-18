.. _azure_multiplesubs:

Running against multiple subscriptions
======================================

The C7N-Org tool supports running policies against multiple subscriptions.  See the
`C7N-Org Readme <https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/c7n_org>`_
for more information.

If you're using an Azure Service Principal for executing c7n-org
you'll need to ensure that the principal has access to multiple
subscriptions. For instructions on creating a Service Principal and granting access
across subscriptions, see :ref:`azure_authentication`

**Note**: There are pending issues with running C7N-Org on Windows. It may be required to
use the ``--debug`` flag when running on Windows.
