.. _ebssnapshots:

EBS - Create and Manage Snapshots
=================================

The following example policy will snapshot all EBS volumes attached to EC2 instances and
copy the instances tags to the snapshot. Then when the snapshots are 7 days old they will
get deleted so you always have a rolling 7 days worth of snapshots.

.. code-block:: yaml

   policies:
     - name: ec2-create-ebs-snapshots
       resource: ec2
       actions:
          - type: snapshot
            copy-tags:
                - CreatorName
                - "Resource Contact"
                - "Resource Purpose"
                - Environment
                - "Billing Cost Center"
                - Name
            tags:
              CloudCustodian: true

     - name: ebs-delete-old-ebs-snapshots
       resource: ebs-snapshot
       filters:
           - type: age
             days: 7
             op: ge
           - "tag:custodian_snapshot": present
       actions:
           - delete
