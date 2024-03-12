.. _accountservicelimit:

Account - Service Limit
=======================

The following example policy will find any service in your region that is using 
more than 50% of the limit and raise the limit for 25%.

.. code-block:: yaml

   policies:
     - name: account-service-limits
       resource: account
       filters:
         - type: service-limit
           threshold: 50
       actions:
         - type: request-limit-increase
           percent-increase: 25

Noted that the ``threshold`` in ``service-limit`` filter is an optional field. If
not mentioned on the policy, the default value is 80.

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
  Services like IAM are not region-based. Custodian will put the limit 
  information only in ``us-east-1``. When running the policy above in multiple 
  regions, the limit of global services will ONLY be raised in us-east-1.

  Additionally, if you want to target any the global services on the policy, you
  will need to target the region as us-east-1 on the policy. Here is an example.

  .. code-block:: yaml

     policies:
       - name: account-service-limits
         resource: account
         conditions:
           - region: us-east-1
         filters:
           - type: service-limit
             services:
               - IAM
             threshold: 50
