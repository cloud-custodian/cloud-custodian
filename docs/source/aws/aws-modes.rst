.. _aws-modes:

AWS Modes
=========

Custodian can run in numerous modes depending on the provider with the default being pull Mode.

- pull:
    Default mode, which runs locally where custodian is run.

  .. c7n-schema:: mode.pull

- periodic:
    Runs Custodian in AWS lambda at user defined cron interval.

  .. c7n-schema:: mode.periodic


- phd:
    Runs custodian in AWS lambda and is triggered by Personal Health Dashboard events. These
    events are triggered by changes in the health of AWS resources, giving you event visibility,
    and guidance to help quickly diagnose and resolve issues. See `Personal Health Dashboard
    <https://aws.amazon.com/premiumsupport/technology/personal-health-dashboard/>`_ for more details.

  .. c7n-schema:: mode.phd


- cloudtrail:
    Runs custodian in AWS lambda and is triggered by cloudtrail events. This allows
    you to apply your policies as soon as events occur. Cloudtrail creates an event for every
    api call that occurs in your aws account. See `Cloudtrail <https://aws.amazon.com/cloudtrail/>`_
    for more details.

  .. c7n-schema:: mode.cloudtrail


- ec2-instance-state:
    Runs custodian in AWS lambda and is triggered by ec2 instance state changes. This is useful if you
    have policies that are specific to ec2. See `EC2 lifecycles
    <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html>`_ for more details.

  .. c7n-schema:: mode.ec2-instance-state


- asg-instance-state:
    Runs custodian in AWS lambda and is triggered by asg instance state changes. This is useful if you
    have policies that are specific to asg. See `ASG lifecycle hooks
    <https://docs.aws.amazon.com/autoscaling/ec2/userguide/lifecycle-hooks.html>`_ for more details.

  .. c7n-schema:: mode.asg-instance-state


- guard-duty:
    Runs custodian in AWS lambda and is triggered by guard-duty responses. AWS Guard Duty is a threat
    detection service that continuously monitors for malicious activity and unauthorized behavior. This mode
    allows you to execute polcies when various alerts are created by AWS Guard Duty. See `Guard Duty
    <https://aws.amazon.com/guardduty/>`_ for more details.

 .. c7n-schema:: mode.guard-duty


- config-rule:
    Runs custodian in AWS lambda and gets triggered by AWS config when there are configuration changes
    of your AWS resources. This is useful if you have policies that enforce certain configurations or
    want to get notified based on certain configuration changes. See `AWS Config
    <https://aws.amazon.com/config/>`_ for more details.

  .. c7n-schema:: mode.config-rule


