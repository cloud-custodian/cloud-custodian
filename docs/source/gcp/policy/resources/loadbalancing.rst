Load Balancing resources
========================

TBD: information about environment variables

.. code-block:: yaml

    policies:
        - name: all-lb-addresses
          description: |
            List of Load Balancing Addresses
          resource: gcp.loadbalancer-address
        - name: all-lb-url-maps
          description: |
            List of Load Balancing Url Maps
          resource: gcp.loadbalancer-url-map
        - name: all-lb-target-tcp-proxies
          description: |
            LoadBalancingTargetTcpProxyTest
          resource: gcp.loadbalancer-target-tcp-proxy
        - name: all-lb-target-ssl-proxies
          description: |
            Test
          resource: gcp.loadbalancer-target-ssl-proxy
        - name: all-lb-ssl-policies
          description: |
            Test
          resource: gcp.loadbalancer-ssl-policy
        - name: all-lb-ssl-certificates
          description: |
            Test
          resource: gcp.loadbalancer-ssl-certificate
        - name: all-lb-target-https-proxies
          description: |
            Test
          resource: gcp.loadbalancer-target-https-proxy
        - name: all-lb-backend-buckets
          description: |
            Test
          resource: gcp.loadbalancer-backend-bucket
        - name: all-lb-https-health-checks
          description: |
            Test
          resource: gcp.loadbalancer-https-health-check
        - name: all-lb-http-health-checks
          description: |
            Test
          resource: gcp.loadbalancer-http-health-check
        - name: all-lb-health-checks
          description: |
            Test
          resource: gcp.loadbalancer-health-check
        - name: all-lb-target-http-proxies
          description: |
            Test
          resource: gcp.loadbalancer-target-http-proxy
        - name: all-lb-backend-services
          description: |
            Test
          resource: gcp.loadbalancer-backend-service
        - name: all-lb-target-instances
          description: |
            Test
          resource: gcp.loadbalancer-target-instance
        - name: all-lb-target-pools
          description: |
            Test
          resource: gcp.loadbalancer-target-pool
        - name: all-lb-forwarding-rules
          description: |
            Test
          resource: gcp.loadbalancer-forwarding-rule
        - name: all-lb-global-forwarding-rules
          description: |
            Test
          resource: gcp.loadbalancer-global-forwarding-rule
        - name: all-lb-global-addresses
          description: |
            Test
          resource: gcp.loadbalancer-global-address

