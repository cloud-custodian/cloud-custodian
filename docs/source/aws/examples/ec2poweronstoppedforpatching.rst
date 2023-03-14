.. _ec2poweronstoppedforpatching:

EC2 - Power On For Scheduled Patching
=====================================

The following example policies will automatically create CloudWatch cron rate
triggered Lambda functions in your account and region. The Lambda functions will
be triggered on the cron rate expression schedule you provide in the mode section
of the policy. The following example policies find all EC2 instances that are
both in a stopped state, and have a tag called ``Patch Group`` with a value of
``Linux Dev``.  Those instances are then started and tagged with an additional
tag of ``PowerOffWhenDone`` and a value of ``True`` so that they can be stopped
again after the patching window. Then all instances with the ``Linux Dev`` Patch
Group get another tag called ``PatchingInProgress`` with a value of ``True``.
The PatchingInProgress tag can be used by other policies such as offhours policies
where the presence of that tag would exclude it from being stopped by the offhours.
When the patching window is done the last 2 policies in this example will remove
the PatchingInProgress tag from all instances in that group and remove the
PowerOffWhenDone tag and stop those instances that were previously stopped. The
cron expressions for this example read as the following:
cron(0 3 ? 1/1 SUN#1 \*) means trigger on the 1st Sunday of every month at 3:00 UTC
then cron(0 13 ? 1/1 SUN#1 \*) is the same day at 13:00 UTC which allows for a 10
Hour patching window.  Learn more on AWS cron rate expressions
https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html

.. code-block:: yaml

   policies:

     - name: power-on-patch-group-linux-dev
       resource: ec2
       mode:
            type: periodic
            schedule: "cron(0 3 ? 1/1 SUN#1 *)"
       filters:
            - "State.Name": stopped
            - type: value
              key: tag:Patch Group
              op: eq
              value: "Linux Dev"
       actions:
            - start
            - type: tag
              key: PowerOffWhenDone
              value: "True"

     - name: patching-exception-tag-linux-dev
       resource: ec2
       mode:
            type: periodic
            schedule: "cron(0 3 ? 1/1 SUN#1 *)"
       filters:
            - type: value
              key: tag:Patch Group
              op: eq
              value: "Linux Dev"
       actions:
            - type: tag
              key: PatchingInProgress
              value: "True"

     - name: patching-exception-removal-linux-dev
       resource: ec2
       mode:
            type: periodic
            schedule: "cron(0 13 ? 1/1 SUN#1 *)"
       filters:
            - type: value
              key: tag:Patch Group
              op: eq
              value: "Linux Dev"
       actions:
            - type: unmark
              tags: ["PatchingInProgress"]

     - name: power-down-patch-group-linux-dev
       resource: ec2
       mode:
            type: periodic
            schedule: "cron(0 13 ? 1/1 SUN#1 *)"
       filters:
            - "State.Name": running
            - "tag:PowerOffWhenDone": present
            - type: value
              key: tag:Patch Group
              op: eq
              value: "Linux Dev"
       actions:
            - stop
            - type: unmark
              tags: ["PowerOffWhenDone"]

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
