.. _actions:

Generic Actions
===============

The following actions can be applied to all policies for all resources. See the
provider specific resource references.

Webhook Action
--------------

The webhook action allows invoking a webhook with information about your resources.

You may initiate a call per resource, or a call referencing a batch of resources.
Additionally you may define the body and query string using JMESPath references to
the resource or resource array.

.. c7n-schema:: aws.ec2.actions.webhook


JMESPath queries for query-params, headers and body will have access to the following data:

.. code-block::

    {
        'account_id',
        'region',
        'execution_id',
        'execution_start',
        'policy',
        'resource',  ─▶ if Batch == false
        'resources', ─▶ if Batch == true
    }


Examples:

.. code-block:: yaml

    actions:
     - type: webhook
       url: http://foo.com?hook-id=123    ─▶ Call will default to POST
       query-params:                      ─▶ Additional query string query-params
          resource_name: resource.name    ─▶ Value is a JMESPath query into resource dictionary
          policy_name: policy.name

    actions:
      - type: webhook
        url: http://foo.com
        batch: true                          ─▶ Single call for full resource array
        body: 'resources[].name'             ─▶ JMESPath will reference array of resources
        query-params:
          count: 'resources[] | length(@)'   ─▶ Include resource count in query string
          static-value: '`foo`'              ─▶ JMESPath string literal in ticks

    actions:
      - type: webhook
        url: http://foo.com
        batch: true
        batch-size: 10
        method: POST
        headers:
            static-value: '`foo`'             ─▶ JMESPath string literal in ticks
        query-params:
            count: 'resources[] | length(@)'
