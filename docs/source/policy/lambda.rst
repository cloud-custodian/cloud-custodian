.. _lambda:

Lambda Support
--------------

Lambda provides for powerful realtime event based code execution in
response to infrastructure and application behavior. A number of
different Amazon services can be used as event sources.

CloudWatch Events
#################

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
===========================

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
=============

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

Config Rules
############

`AWS Config rules
<http://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules.html>`_
allow you to invoke logic in response to configuration changes in your AWS
environment, and Cloud Custodian is the easiest way to write and provision
Config rules.

In this section we'll look at how we would deploy the :ref:`quickstart
<quickstart>` example using Config. Before you proceed, make sure you've
removed the ``Custodian`` tag from any EC2 instance left over from the
quickstart.

First, modify ``custodian.yml`` to specify a mode type of ``config-rule``.
You'll also need the ARN of an IAM role to assume when running the Lambda that
Custodian is going to install for you.

.. code-block:: yaml

    policies:
      - name: my-first-policy
        mode:
            type: config-rule
            role: arn:aws:iam::123456789012:role/some-role
        resource: ec2
        filters:
          - "tag:Custodian": present
        actions:
          - stop

Now deploy the policy:

.. code-block:: bash

    custodian run -s . custodian.yml

That should give you log output like this::

    2017-01-25 05:43:01,539: custodian.policy:INFO Provisioning policy lambda my-first-policy
    2017-01-25 05:43:04,683: custodian.lambda:INFO Publishing custodian policy lambda function custodian-my-first-policy

Go check the AWS console to see the Lambda as well as the Config rule that
Custodian created. The Config rule should be listed as "Compliant" or "No
results reported" (if not, be sure you removed the ``Custodian`` tag from any
instance left over from the quickstart).

Now for the fun part! With your new policy installed, go ahead and create an
EC2 instance with a ``Custodian`` tag (any non-empty value), and wait (events
from Config are effectively delayed 15m up to 6hrs on tag changes). If all goes
well, you should eventually see that your new custom Config rule notices the
EC2 instance with the ``Custodian`` tag, and stops it according to your policy.

Congratulations! You have now installed your policy to run under Config rather
than from your command line.
