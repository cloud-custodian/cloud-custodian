.. _instanceremovetagcompute:

Instance - Query and remove the specified tag from all the instances
====================================================================

The following example policy queries and removes the tag from the instances


.. code-block:: yaml

    policies:
     - name: remove-tag-from-instances
       description: |
         Query and remove tag from the instances
       resource: oci.instance
       actions:
           - type: remove-tag
             defined_tags: ['organization.team', 'environment.test']
             freeform_tags: ['cloud_custodian']
