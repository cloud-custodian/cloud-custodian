.. _elbdeleteinetfacing:

ELB - Delete New Internet-Facing ELBs
=====================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a user creates a new classic Elastic Load Balancer. If the ELB is set to
be internet-facing then delete it right away at launch. This provides near 
real-time auto-remediation (typically within 1-2 mins) of the ELB being created.
Having such a quick auto-remediation action greatly reduces an attack window!
By notifying the customer who tried to perform the action it helps drive user
behaviour as well and lets them know why their ELBs keep deleting at launch! ;)

.. code-block:: yaml

   policies:

     - name: elb-delete-new-internet-facing
       resource: elb
       mode:
         type: cloudtrail
         events:
            - CreateLoadBalancer
       description: |
         Any newly created Classic Load Balanacers launched with
         a internet-facing schema will be deleted right away.
       filters:
         - type: event
           key: "detail.requestParameters.scheme"
           op: eq
           value: "internet-facing"
       actions:
         - delete
         - type: notify
           template: default.html
           priority_header: 1
           subject: "Deleted New Internet-Facing ELB - [custodian {{ account }} - {{ region }}]"
           violation_desc: "Internet-Facing ELBs are not allowed and are deleted at launch."
           action_desc: |
              "Actions Taken: Your new ELB has been deleted.
              Please launch a new non-internet-facing ELB"
           to:
              - CloudCustodian@Company.com
              - event-owner
           transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
              region: us-east-1

By including ``- event-owner`` in the notify's to: field it tells Cloud Custodian
to extract the id of the user who made the API call for the event and email them.
Being that the above policy runs in a cloudtrail mode the API call's metadata event
is present which is why the example uses event-owner.  If you were to remove the ``mode:``
statement on the example policy and run it in a poll mode instead you could change
``- event-owner`` to ``- resource-owner`` which would rely on the resources tags for
a id or email to send the notification to as no API event would be available at that time.
Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
