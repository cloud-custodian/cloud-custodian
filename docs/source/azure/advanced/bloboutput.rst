.. _azure_bloboutput:

Blob Storage Output
===================

Writing Custodian Output to Azure Blob Storage
----------------------------------------------

You may pass the URL to a blob storage container as the output path to Custodian.
You must change the URL prefix from https to azure.

    .. code-block:: sh

        custodian run -s azure://mystorage.blob.core.windows.net/logs mypolicy.yml

Custodian will use your current credentials to discover the storage account and
load the storage account keys.  The account must be in your current subscription.