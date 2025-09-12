ELB - SSL Blacklist
===================

.. code-block:: yaml

  policies:
   - name: elb-ssl-blacklist
     description: |
       HTTPS/SSL ELBs should not have blacklisted ciphers/protocols
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
