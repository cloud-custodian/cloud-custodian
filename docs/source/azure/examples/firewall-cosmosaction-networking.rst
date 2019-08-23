Firewall - Update CosmosDB Rules
============================================

In this example we identify Cosmos DB accounts that either have no firewall
configured or which have one configured which is allowing access outside of
expected ranges.

We then reconfigure that firewall to known-safe defaults which include a bypass for
all of the Azure Cloud as well as additional space in our data center.

Virtual network rules are not specified so they will not be modified.

.. code-block:: yaml

 policies:
  - name: cosmos-firewall-enable
    description: |
      Find all incorrect firewalls and enable
      with a set of defaults
    resource: azure.cosmosdb
    filters:
      - or:
        - type: value
          key: properties.ipRangeFilter
          value: empty  # The firewall is disabled

        - not:
          - type: firewall-rules
            only:       # Should *only* allow access within the specified maximums here
              - 19.0.0.0/16
              - 20.0.1.2
              - ServiceTags.AzureCloud

    actions:
      - type: set-firewall-rules
        append: False
        bypass-rules:   # Enable firewall and allow all Azure Cloud
          - AzureCloud
          - Portal
        ip-rules:       # and some external IP space
          - 19.0.0.0/16
          - 20.0.1.2



