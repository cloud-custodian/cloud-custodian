.. _oci_logging:

Logging and Output
==================

Writing Custodian Logs to Object Storage
-----------------------------------------

You can output logs and resource records to Object Storage.
By default, Custodian will add the policy name and date as the prefix to the blob.:

    .. code-block:: sh

        custodian run -s oci://<Bucket_Name>/<Optional_Prefix_Name>/ <policy file>

In order to send data to a bucket in a different profile you can use query params

    .. code-block:: sh

        custodian run -s oci://<Bucket_Name>/<Optional_Prefix_Name>/?profile=<NAME> <policy file>

The bucket must already exist otherwise an error will be thrown.

Writing Custodian Logs to OCI Logging Service
---------------------------------------------

You can send the logs to OCI Logging service. In order to use logging service,
Custodian needs to know the compartment ID where the logs need to be sent. This can
be achieved by either providing it as a query param "OCI_LOG_COMPARTMENT_ID" or
an environment variable "OCI_LOG_COMPARTMENT_ID" must be set. The query param will
take precedence over the environment variable.
Custodian will create the log group if it doesn't already exist and create a log
with the same name as the policy name. The log retention period will be the default value.
More details `here. <https://docs.oracle.com/en-us/iaas/api/#/en/logging-management/20200531/datatypes/CreateLogDetails>`_

#. Using query param to set logging compartment ID

    .. code-block:: sh

        custodian run --output-dir . --log-group=oci://custodian-test?OCI_LOG_COMPARTMENT_ID=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value <policy file>

#. Using environment variable to set logging compartment ID

    .. code-block:: sh

        export OCI_LOG_COMPARTMENT_ID=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value
        custodian run --output-dir . --log-group=oci://custodian-test <policy file>

The above commands will create a log group called "custodian-test" and push logs there

In order to send data to a log group in a different profile you can use query params

    .. code-block:: sh

        export OCI_LOG_COMPARTMENT_ID=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value
        custodian run --output-dir . --log-group=oci://custodian-test?profile=<NAME> <policy file>


