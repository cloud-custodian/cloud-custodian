.. _accountservicelimit:

Account - Service Limit
=======================

The following example policy will find any service in your region that is using
more than 50% of the limit and raise the limit for 25%. Any service quotas that
have an open support case will be skipped.

.. code-block:: yaml

   policies:
     - name: account-service-limits
       resource: aws.service-quota
       filters:
         - UsageMetric: present
         - type: usage-metric
           limit: 50
         - type: request-history
           key: "[].Status"
           value: CASE_OPENED
           value_type: swap
           op: not-in
       actions:
         - type: request-increase
           multiplier: 1.25

As there are numerous services available in AWS, you have the option to specify
the services you wish to include or exclude, thereby preventing prolonged execution times
and unnecessary API calls. Please utilize either of the attributes:
"include_service_codes" or "exclude_service_codes". This special filter only works for
`aws.service-quota`. An example is provided below.

.. code-block:: yaml

   policies:
     - name: service-quota-usage
       resource: aws.service-quota
       query:
         - include_service_codes:
             - ec2

Global Services
  Some AWS services, such as IAM, are global and not region-specific.
  Cloud Custodian can only access their quota information in ``us-east-1``.
  In order to target global services like IAM, the policy must run in the ``us-east-1`` region.


  .. code-block:: yaml

     policies:
       - name: iam-service-quotas
         resource: aws.service-quota
         conditions:
           - region: us-east-1
         query:
           - include_service_codes:
               - iam
         filters:
           - UsageMetric: present
           - type: usage-metric
             limit: 50
