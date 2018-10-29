.. _azure_bloboutput:

Blob Storage Output
===================

Writing Custodian Output to Azure Blob Storage
----------------------------------------------

You may pass the URL to a blob storage container as the output path to Custodian.
You must change the URL prefix from https to azure.

By default, Custodian will add the policy name and date as the prefix to the blob.

    .. code-block:: sh

        custodian run -s azure://mystorage.blob.core.windows.net/logs mypolicy.yml

In addition, you can use `pyformat` syntax to format the output prefix.
This example is the same structure as the default one.

    .. code-block:: sh

        custodian run -s azure://mystorage.blob.core.windows.net/logs/{policy}/{now:%Y/%m/%d/%H/} mypolicy.yml

Use `{account_id}` for Subscription ID.


Authentication to Storage
-------------------------

The account working with storage will require `Blob Data Contributor` on either the storage account
or a higher scope.