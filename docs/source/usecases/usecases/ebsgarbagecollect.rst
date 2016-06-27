EBS - Garbage Collect Unattached Volumes
========================================

  .. code-block:: yaml

     - name: ebs-mark-unattached-deletion
       resource: ebs
       comments: |
         Mark any unattached EBS volumes for deletion in 30 days.
         Volumes set to not delete on instance termination do have
         valid use cases as data drives, but 99% of the time they
         appear to be just garbage creation.
       filters:
         - Attachments: []
         - "tag:maid_status": absent
       actions:
         - type: mark-for-op
           op: delete
           days: 30

     - name: ebs-unmark-attached-deletion
       resource: ebs
       comments: |
         Unmark any attached EBS volumes that were scheduled for deletion
         if they are currently attached
       filters:
         - type: value
           key: "Attachments[0].Device"
           value: not-null
         - "tag:maid_status": not-null
       actions:
         - unmark
   
     - name: ebs-delete-marked
       resource: ebs
       comments: |
         Delete any attached EBS volumes that were scheduled for deletion
       filters:
         - type: marked-for-op
           op: delete
       actions:
         - delete
