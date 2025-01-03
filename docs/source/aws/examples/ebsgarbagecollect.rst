EBS - Garbage Collect Unattached Volumes
========================================

Use the ``mark-for-op`` action to mark a resource for action later. One common
pattern to follow is to mark a resource with an operation (example: delete) in
n days. In the subsequent days leading up to the marked date, run a unmark or
untag policy if the resource has become compliant in the mean time.

You can use this principle to implement garbage collection on resources. In this
example, Custodian will first mark all unattached EBS volumes for deletion. The
next policy will then unmark any volume that has been attached and has the
``maid_status`` tag, indicating that it had been previously marked. Finally, the
third policy will filter in any resources that have been marked and run the
``delete`` action.

It is important to note that the delete policy will need to be run on the day that
the resource is marked for, else the resource will still exist in the account.
The mark operation only tags the resource with metadata about the upcoming operation.
Operationally, the policy still must be executed on the day that is specified in
the tag.

Note: all resources that are ``marked-for-op`` up to and including the current
date will be filtered in when utilizing the ``marked-for-op`` filter.

  .. code-block:: yaml

    policies:
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
