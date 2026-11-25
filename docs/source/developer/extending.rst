.. _developer-extending:

Extending Cloud Custodian: Resources, Filters, and Actions
==========================================================

This guide outlines how to extend Cloud Custodian by registering new resource types, filters, actions, and custom decorators.

Overview
--------

Cloud Custodian uses a plugin architecture where resources, filters, and actions are registered with provider-specific registries.

* **Resource Types**: Represent cloud infrastructure components (e.g., AWS EC2 instances, Azure VMs, GCP Buckets).
* **Filters**: Evaluate resource state or event context against policy criteria.
* **Actions**: Perform mutations, governance remediation, or notification operations on matched resources.

Resource Type Metadata
----------------------

Resource definitions bind a provider-native SDK query model to Custodian's internal schema.

TypeInfo Schema
~~~~~~~~~~~~~~~

Resource metadata is defined via the ``TypeInfo`` structure on the ``QueryResourceManager``:

.. code-block:: python

   from c7n.query import QueryResourceManager, TypeInfo
   from c7n.provider import resources

   @resources.register('my_resource')
   class MyResource(QueryResourceManager):

       class resource_type(TypeInfo):
           service = 'myservice'
           enum_spec = ('list_resources', 'Resources', None)
           id = 'ResourceId'
           name = 'ResourceName'
           date = 'CreationDate'
           dimension = 'ResourceName'
           filter_name = 'ResourceNames'
           filter_type = 'list'

Required Metadata Fields
~~~~~~~~~~~~~~~~~~~~~~~~

* ``service``: Cloud provider client service identifier.
* ``enum_spec``: Tuple defining ``(api_operation, response_key, query_params)``.
* ``id``: Unique field name in resource dictionary representing the primary key.
* ``name``: Display name or taggable name property.
* ``date``: Creation timestamp field name (used by age filters).

Filter Architecture
-------------------

Filters derive from ``c7n.element.Element`` or ``c7n.filters.core.Filter``.

Base Filter Contract
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from c7n.filters import Filter
   from c7n.utils import type_schema

   class CustomResourceFilter(Filter):
       """Custom filter to check resource attributes."""

       schema = type_schema(
           'my-custom-filter',
           **{'state': {'type': 'string'}}
       )
       permissions = ('myservice:DescribeResources',)

       def process(self, resources, event=None):
           results = []
           target_state = self.data.get('state')
           for r in resources:
               if r.get('State') == target_state:
                   results.append(r)
           return results

Key Responsibilities
~~~~~~~~~~~~~~~~~~~~

1. **Schema Validation**: Define ``schema`` using ``type_schema()`` to enforce JSON schema validation during policy load.
2. **IAM Permissions**: Declare required provider API permissions in ``permissions``.
3. **Execution**: Implement ``process(resources, event=None)`` returning the list of matching resource dictionaries.

Action Architecture
-------------------

Actions implement mutations or operational hooks on resources.

Base Action Contract
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from c7n.actions import Action
   from c7n.utils import type_schema

   class CustomResourceAction(Action):
       """Custom action to remediate resource state."""

       schema = type_schema(
           'my-custom-action',
           **{'tag_key': {'type': 'string'}, 'tag_value': {'type': 'string'}}
       )
       permissions = ('myservice:TagResource',)

       def process(self, resources):
           client = self.manager.get_client()
           tag_key = self.data.get('tag_key')
           tag_value = self.data.get('tag_value')
           
           for r in resources:
               client.tag_resource(
                   ResourceId=r[self.manager.resource_type.id],
                   Tags={tag_key: tag_value}
               )

Execution Modes & Decorators
----------------------------

Custodian actions and policies utilize execution mode wrappers for serverless or event-driven execution.

Functional & Execution Mode Wrappers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``@execution_mode``: Decorator specifying supported policy execution modes (e.g., ``pull``, ``cloudtrail``, ``periodic``).
* ``@deprecated``: Flags legacy filters/actions for future deprecation warnings.
* Lazy Validation: ``Element.validate()`` executes prior to ``process()`` to perform early configuration verification.
