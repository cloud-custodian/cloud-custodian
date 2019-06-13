.. _asg:

Auto Scaling Groups (ASG)
=========================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``security-group``
  Filter for ASG's that have a certain security group.

  .. c7n-schema:: aws.asg.filters.security-group

``subnet``
  Filter on ASG's

  .. c7n-schema:: aws.asg.filters.subnet


``launch-config``
  Filter ASG by launch config attributes.

  .. c7n-schema:: aws.asg.filters.launch-config

``valid``
  Filters ASG's to find those that are structurally valid.

  .. c7n-schema:: aws.asg.filters.valid


``invalid``
  Filters ASG's to find those that are structurally invalid.

  .. c7n-schema:: aws.asg.filters.invalid


``not-encrypted``
  Check if an ASG is configured to have unencrypted volumes.

  .. c7n-schema:: aws.asg.filters.not-encrypted


``image-age``
  Filter ASG by image age (in days). **Deprecated** use `image`

  .. c7n-schema:: aws.asg.filters.image-age


``image``
  Filter by ASG image

  .. c7n-schema:: aws.asg.filters.image


``vpc-id``
  Filters ASG based on the VpcId

  .. c7n-schema:: aws.asg.filters.vpc-id

``progagated-tags``
  Filter ASG based on propagated tags

  .. c7n-schema:: aws.asg.filters.propagated-tags

``capacity-delta``
  Filter returns ASG that have less instances than desired or required

  .. c7n-schema:: aws.asg.filters.capacity-delta

``user-data``
  Filter for ASG's with launch configs containing user data matching the value given.

  .. c7n-schema:: aws.asg.filters.user-data


``offhour`` or ``OffHour``
  Turn resources off based on a schedule.

  .. c7n-schema:: aws.asg.filters.offhour

``onhour`` or ``onhour``
  Turn resources on based on a schedule.

  .. c7n-schema:: aws.asg.filters.onhour


Actions
-------

``tag-trim``
  Trim the number of tags to avoid hitting tag limits.

    .. c7n-schema:: aws.asg.actions.tag-trim

``resize``
  Resize the min/max/desired instances in an ASG.

    .. c7n-schema:: aws.asg.actions.resize

``remove-tag`` or ``untag`` or ``unmark``
  Removes tag from ASG.

  .. c7n-schema:: aws.asg.actions.remove-tag


``tag`` or ``mark``
  Create or update tag on ASG.

  .. c7n-schema:: aws.asg.actions.tag

``propagate-tags``
  Propagate tags to an ASG instances. In AWS changing an ASG tag does not propagate to instances. This action exists to do that, and can also trim older tags not present on the ASG anymore that are still present on instances.

  .. c7n-schema:: aws.asg.actions.propagate-tags


``rename-tag``
  Rename a tag on an AutoScaleGroup.

  .. c7n-schema:: aws.asg.actions.rename-tag

``mark-for-op``
  Tag ASG for an operation.

  .. c7n-schema:: aws.asg.actions.mark-for-op

``suspend``
  Multistep process to stop an ASG. Suspend processes, note load balancer in tag, detach load balancer, and then stop instances.

  .. c7n-schema:: aws.asg.actions.suspend


``resume``
  Multi-step process to resume an ASG. Start any stopped EC2 instances, reattach ELB, and resume ASG processes.

  .. c7n-schema:: aws.asg.actions.resume


``delete``
  Delete ASG.

  .. c7n-schema:: aws.asg.actions.delete


Launch Configs
++++++++++++++

``delete``
  Delete a launch configuration.

  .. c7n-schema:: aws.asg.actions.delete
