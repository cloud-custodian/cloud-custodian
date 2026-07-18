ELB - SSL Whitelist
===================

.. code-block:: yaml

  policies:
   - name: elb-ssl-whitelist
     description: |
       HTTPS/SSL ELBs should only have whitelisted ciphers/protocols
     resource: elb
     mode:
       type: cloudtrail
       events:
         - CreateLoadBalancer
         - CreateLoadBalancerPolicy
         - SetLoadBalancerPoliciesOfListener
     filters:
       - type: ssl-policy
         whitelist: &POLICY
           - Protocol-TLSv1
           - Protocol-TLSv1.1
           - Protocol-TLSv1.2
     actions:
       - type: set-ssl-listener-policy
         name: CustodianEnforcedPolicy
         attributes: *POLICY
