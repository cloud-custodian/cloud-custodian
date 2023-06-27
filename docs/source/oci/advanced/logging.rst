.. _oci_logging:

Logging and Output
==================

Writing Custodian Logs to Object Storage
-----------------------------------------

You can output logs and resource records to Object Storage.
By default, Custodian will add the policy name and date as the prefix to the blob.:

    .. code-block:: sh

        custodian run -s oci://<Bucket_Name>/<Optional_Folder_Name>/ <policy file>

In order to send data to a bucket in a different profile you can use query params

    .. code-block:: sh

        custodian run -s oci://<Bucket_Name>/<Optional_Folder_Name>/?profile=<NAME> <policy file>

If the bucket does not exist then Custodian will try to create a bucket in the
compartment identified by the environment variable "OCI_LOG_COMPARTMENT_ID".

Writing Custodian Logs to OCI Logging Service
---------------------------------------------

You can send the logs to OCI Logging service. In order to use logging service,
the environment variable "OCI_LOG_COMPARTMENT_ID" must be set with the value of
the compartment id where the logs need to be sent.
Custodian will create the log group if it doesn't already exist and create a log
with the same name as the policy name. The log retention period will be the default value.
More details `here. <https://docs.oracle.com/en-us/iaas/api/#/en/logging-management/20200531/datatypes/CreateLogDetails>`_

    .. code-block:: sh

        export OCI_LOG_COMPARTMENT_ID=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value
        custodian run --output-dir . --log-group=oci://custodian-test <policy file>

The above command will create a log group called "custodian-test" and push logs there

In order to send data to a log group in a different profile you can use query params

    .. code-block:: sh

        export OCI_LOG_COMPARTMENT_ID=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value
        custodian run --output-dir . --log-group=oci://custodian-test?profile=<NAME> <policy file>


