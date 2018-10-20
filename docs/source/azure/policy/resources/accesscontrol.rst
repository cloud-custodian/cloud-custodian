.. _azure_access_control:

Access Control
==============

Cloud custodian supports both azure role assignments and role definitions.

In order to get the principal name, display name, and AAD type (User, Service Principal, etc) of role assignments the
method of authorization must have the necessary permissions to read from the Microsoft AAD Graph. For Service Principal
Authorization the Service Principal must have the permissions to `read all users' full profiles`. Azure CLI
authentication will provide the necessary permissions to run the policy locally. Basic token authentication will not
provide the necessary permissions. 

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `RoleAssignment <https://docs.microsoft.com/en-us/python/api/azure.mgmt.authorization.models.roleassignment?view=azure-python>`_
    - Model: `RoleDefinition <https://docs.microsoft.com/en-us/python/api/azure.mgmt.authorization.models.roledefinition?view=azure-python>`_

- ``role``
  Filters Role Assignments based on name of Role Definition

  .. c7n-schema:: RoleFilter
      :module: c7n_azure.resources.access_control

- ``resource-access``
  Filter Role Assignments based on access to an azure resource

  .. c7n-schema:: ResourceAccessFilter
      :module: c7n_azure.resources.access_control

- ``scope``
  Filter Role Assignments by scope access

  .. c7n-schema:: ScopeFilter
      :module: c7n_azure.resources.access_control


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)
- ``delete``
  Deletes role assignment

Example Policies
----------------

Return role assignments with the Owner role.

.. code-block:: yaml

    policies:
       - name: assignment-by-role
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: eq
              value: Owner

Return all assignments with the Owner role that have access to virtual machines. For the
resource-access filter, the related resource can be any custodian supported azure resource other than
azure.roleassignments or azure.roledefinitions.

.. code-block:: yaml

    policies:
       - name: assignment-by-role-and-resource
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: eq
              value: Owner
            - type: resource-access
              relatedResource: azure.vm

Return all assignments with the Owner role that have access to virtual machines in westus2:

.. code-block:: yaml

    policies:
       - name: assignment-by-role-and-resource
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: eq
              value: Owner
            - type: resource-access
              relatedResource: azure.vm
              key: location
              op: eq
              value: westus2

Return assignments with the principal name custodian@example.com:

.. code-block:: yaml

     policies:
       - name: assignment-by-principal-name
         resource: azure.roleassignment
         filters:
            - type: value
              key: principalName
              op: eq
              value: custodian@example.com

Return role definitions that explicitly have the permission to read authorization objects (role
assignments, role definitions, etc). If a role definition inherits permissions (e.g. by having * permissions)
they are not returned in this filter.

.. code-block:: yaml

    policies:
        - name: role-definition-permissions
          resource: azure.roledefinition
          filters:
            - type: value
              key: properties.permissions[0].actions
              value: Microsoft.Authorization/*/read
              op: contains

Delete the assignment with principal name custodian@example.com. The permissions required to run the
delete action requires delete permissions to Microsoft.Authorization. The built-in role with the necessary permissions
is Owner.

.. code-block:: yaml

     policies:
       - name: delete-assignment-by-principal-name
         resource: azure.roleassignment
         filters:
            - type: value
              key: principalName
              op: eq
              value: custodian@example.com
         actions:
            - type: delete

Return all role assignments with the Subscription level scope access.

.. code-block:: yaml

    policies:
       - name: assignments-subscription-scope
         resource: azure.roleassignment
         filters:
            - type: scope
              value: subscription

Return all role assignments with the Resource Group level scope access.

.. code-block:: yaml

    policies:
       - name: assignments-resource-group-scope
         resource: azure.roleassignment
         filters:
            - type: scope
              value: resource-group

Return all role assignments with scope level access other than Subscription or Resource Group.

.. code-block:: yaml

    policies:
       - name: assignments-other-level-scope
         resource: azure.roleassignment
         filters:
            - not: 
              - type: scope
                value: subscription
            - not:
              - type: scope
                value: resource-group

Return all service principal role assignments with the Subscription level scope access.

.. code-block:: yaml

    policies:
       - name: service-principal-assignments-subscription-scope
         resource: azure.roleassignment
         filters:
            - type: value
              key: aadType
              op: eq
              value: ServicePrincipal
            - type: scope
              value: subscription
            