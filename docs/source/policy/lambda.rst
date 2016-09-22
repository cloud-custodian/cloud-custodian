.. _lambda:

Lambda Support
--------------

Lambda provides for powerful realtime event based code execution in
response to infrastructure and application behavior. A number of
different Amazon services can be used as event sources.

CloudWatch Events
##################

CloudWatch Events (CWE) is a general event bus for AWS infrastructure. Currently,
it covers several major sources of information: CloudTrail API calls
over a poll period on CloudTrail delivery, real-time instance status
events, autoscale group notifications, and scheduled/periodic events.

CloudTrail provides a very rich data source over the entire range
of AWS services exposed via the audit trail that allows Custodian to define effective
realtime policies against any AWS product.

Additionally, for EC2 instances we can provide mandatory policy
compliance - this means the non-compliant resources never
became available.

Cloud Custodian Integration
###########################

Custodian provides for policy level execution against any CWE event
stream. Each Custodian policy can be deployed as an independent Lambda
function. The only difference between a Custodian policy that runs in
Lambda and one that runs directly from the CLI in poll mode
is the specification of the subscription of the events in the mode config block of the policy.

Internally Custodian will reconstitute current state for all the resources
in the event, execute the policy against them, match against the
policy filters, and apply the policy actions to matching resources.

:ref:`Mu<mu>` is the letter after Lambda, Lambda is a keyword in python.

Configuration
#############

Examples

.. code-block:: yaml

   policies:

     # Cloud Watch Events over CloudTrail api calls (1-15m trailing)
     - name: ec2-tag-compliance
       resource: ec2

       # The mode block is the only difference between a Custodian policy that
       # runs in reactive/push mode via lambda and one that runs in poll mode.
       mode:
         type: cloudtrail
         events:
          - RunInstances

         # Note because the total AWS API surface area is so large
         # most CloudTrail API event subscriptions need two additional
         # fields.
         #
         # For CloudTrail events we need to reference the source API call
         # sources:
         #  - ec2.amazonaws.com
         #
         # To work transparently with existing resource policies, we also
         # need to specify how to extract the resource IDs from the event
         # via JMESPath so that the resources can be queried.
         # IDs: "detail.responseElements.instancesSet.items[].instanceId"
         #
         # For very common API calls for policies, some shortcuts have
         # been defined to allow for easier policy writing as for the
         # RunInstances API call above.
         #

       filters:
         - or:
           - tag:required1: absent
           - tag:required2: absent
       actions:
         - stop

     # On EC2 Instance state events (real time, seconds)
     - name: ec2-require-encrypted-volumes
       resource: ec2
       mode:
         type: ec2-instance-state
         events:
         - pending
       filters:
         - type: ebs
           key: Encrypted
           value: False
       actions:
         - mark
         # TODO delete instance volumes that
         # are not set to delete on terminate;
         # currently we have a poll policy that
         # handles this.
         - terminate

     # Periodic Function
     # Syntax for scheduler per http://goo.gl/x3oMQ4
     # Supports both rate per unit time and cron expressions
     - name: s3-bucket-check
       resource: s3
       mode:
         type: periodic
         schedule: "rate(1 day)"
