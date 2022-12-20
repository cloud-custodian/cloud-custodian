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
