.. _elbgarbagecollection:

ELB - Delete Unused Elastic Load Balancers
=====================================================

The following example policy workflow uses the mark-for-op and marked-for-op filters and
actions to chain together a set of policies to accomplish a task.  In this example it
will find any ELB that isn't attached to any instances and tag it with a delete op
and date 14 days out.  The policy workflow will also email the ELB resource owner to
inform them of the upcoming deletion if the ELB remains unused.  If the customer adds
an instance back to their ELB it will get unmarked so it doesn't get deleted.

Note the use of the notify action requires the Cloud Custodian mailer to be installed
and configured.

.. code-block:: yaml

   policies:

    - name: elb-mark-unused-for-deletion
      resource: elb
      description: |
        Mark any ELB with no instances attached for deletion in 14 days.
        Also send an email to the ELB resource owner informing them its unused.
      filters:
        - "tag:maid_status": absent
        - Instances: []
      actions:
        - type: mark-for-op
          tag: maid_status
          op: delete
          days: 14
        - type: notify
          template: default.html
          priority_header: 1
          subject: "ELB - No Instances Attached - [custodian {{ account }} - {{ region }}]"
          violation_desc: "No Instances Are Attached To The Following ELB(s):"
          action_desc: |
            Actions Taken: The unused ELBs have been marked for deletion in 14 if they
            remain unused. If you still need the ELBs listed below, please attach instances
            to them, otherwise please delete them if not needed anymore.
          to:
            - CloudCustodian@Company.com
            - resource-owner
          transport:
            type: sqs
            queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
            region: us-east-1

    - name: elb-unmark-if-in-use
      resource: elb
      description: |
        Remove the maid_status tag from any elb which has instances attached
        so it doesn't get deleted by the following policy
      filters:
        - "tag:maid_status": not-null
        - not:
          - Instances: []
      actions:
        - type: remove-tag
          tags: [maid_status]

    - name: elb-delete-unused
      resource: elb
      description: |
        Delete any marked ELB which has no instances attached
        if it has been that way for 14 days or more.
      filters:
        - type: marked-for-op
          op: delete
      actions:
        - delete
        - type: notify
          template: default.html
          priority_header: 1
          subject: "ELB - Deleted Stale ELB - [custodian {{ account }} - {{ region }}]"
          violation_desc: "No Instances Are Attached To ELB for over 14 days:"
          action_desc: "Actions Taken:  The ELB has been deleted"
          to:
            - CloudCustodian@Company.com
            - resource-owner
          transport:
            type: sqs
            queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
            region: us-east-1
