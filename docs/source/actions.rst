.. _actions:

Generic Actions
===============

The following actions can be applied to all policies for all resources. See the
:ref:`Filters and Actions reference <policy>` for
aws resource-specific actions.

Webhook Action
--------------

The webhook action allows invoking a webhook with information about your resources.

You may initiate a call per resource, or a single call referencing all resources.
Additionally you may define the body and query string using JMESPath references to
the resource or resource array.

.. c7n-schema:: Webhook
    :module: c7n.actions.webhook


JMESPath queries for parameters, headers and body will have access to the following data:

.. code-block:: json

    {
        'account_id',
        'region',
        'execution_id',
        'execution_start',
        'policy',
        'resource', ─▶ if Batch == false
        'resources', ─▶ if Batch == true
    }


Examples:

.. code-block:: yaml

    actions:
     - type: webhook
       url: http://foo.com?hook-id=123  ─▶ Call will default to GET as there is no body
       parameters:                      ─▶ Additional query string parameters
          resource_name: resource.name  ─▶ Value is a JMESPath query into resource dictionary
          policy_name: policy.name

    actions:
      - type: webhook
        url: http://foo.com                  ─▶ Call will default to POST as there is a body
        batch: true                          ─▶ Single call for full resource array
        body: 'resources[].name'             ─▶ JMESPath will reference array of resources
        parameters:
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
        parameters:
            count: 'resources[] | length(@)'
