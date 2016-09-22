ELB - SSL Blacklist
===================

.. code-block:: yaml

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
         blacklist:
           - Protocol-TLSv1
           - Protocol-TLSv1.1
           - Protocol-TLSv1.2
     actions:
       - delete
