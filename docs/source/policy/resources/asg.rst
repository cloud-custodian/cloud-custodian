.. _asg:

Auto Scaling Groups (ASG)
=========================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``security-group``
  Filter for ASG's that have a certain security group.

  .. c7n-schema:: SecurityGroupFilter
      :module: c7n.resources.asg

``subnet``
  Filter on ASG's

  .. c7n-schema:: SubnetFilter
      :module: c7n.resources.asg


``launch-config``
  Filter ASG by launch config attributes.

  .. c7n-schema:: LaunchConfigFilter
      :module: c7n.resources.asg

``valid``
  Filters ASG's to find those that are structurally valid.

  .. c7n-schema:: ValidConfigFilter
      :module: c7n.resources.asg

``invalid``
  Filters ASG's to find those that are structurally invalid.

  .. c7n-schema:: InvalidConfigFilter
      :module: c7n.resources.asg

``not-encrypted``
  Check if an ASG is configured to have unencrypted volumes.

  .. c7n-schema:: NotEncryptedFilter
      :module: c7n.resources.asg

``image-age``
  Filter ASG by image age (in days).

  .. c7n-schema:: ImageAgeFilter
      :module: c7n.resources.asg

``image``
  Filter by ASG image

  .. c7n-schema:: ImageFilter
      :module: c7n.resources.asg

``vpc-id``
  Filters ASG based on the VpcId

  .. c7n-schema:: VpcIdFilter
      :module: c7n.resources.asg

``progagated-tags``
  Filter ASG based on propagated tags

  .. c7n-schema:: PropagatedTagFilter
      :module: c7n.resources.asg

``capacity-delta``
  Filter returns ASG that have less instances than desired or required

  .. c7n-schema:: CapacityDelta
      :module: c7n.resources.asg

``user-data``
  Filter for ASG's with launch configs containing user data matching the value given.

  .. c7n-schema:: UserDataFilter
      :module: c7n.resources.asg


Actions
-------

``tag-trim``
  Trim the number of tags to avoid hitting tag limits.

    .. c7n-schema:: TagTrim
        :module: c7n.resources.asg

``resize``
  Resize the min/max/desired instances in an ASG.

    .. c7n-schema:: Resize
        :module: c7n.resources.asg

``remove-tag`` or ``untag`` or ``unmark``
  Removes tag from ASG.

  .. c7n-schema:: RemoveTag
      :module: c7n.resources.asg

``tag`` or ``mark``
  Create or update tag on ASG.

  .. c7n-schema:: Tag
      :module: c7n.resources.asg

``propagate-tags``
  Propagate tags to an ASG instances. In AWS changing an ASG tag does not propagate to instances. This action exists to do that, and can also trim older tags not present on the ASG anymore that are still present on instances.

  .. c7n-schema:: PropagateTags
      :module: c7n.resources.asg

``rename-tag``
  Rename a tag on an AutoScaleGroup.

  .. c7n-schema:: RenameTag
      :module: c7n.resources.asg

``mark-for-op``
  Tag ASG for an operation.

  .. c7n-schema:: MarkForOp
      :module: c7n.resources.asg

``suspend``
  Multistep process to stop an ASG. Suspend processes, note load balancer in tag, detach load balancer, and then stop instances.

  .. c7n-schema:: Suspend
      :module: c7n.resources.asg

``resume``
  Multi-step process to resume an ASG. Start any stopped EC2 instances, reattach ELB, and resume ASG processes.

  .. c7n-schema:: Resume
      :module: c7n.resources.asg

``delete``
  Delete ASG.

  .. c7n-schema:: Delete
      :module: c7n.resources.asg

``offhour`` or ``OffHour``
  Turn resources off based on a schedule.
  :py:class:`.c7n.offhours`

  .. c7n-schema:: OffHour
      :module: c7n.resources.asg

``onhour`` or ``onhour``
  Turn resources on based on a schedule.
  :py:class:`.c7n.offhours`

  .. c7n-schema:: OnHour
      :module: c7n.resources.asg


Launch Configs
++++++++++++++

``delete``
  Delete a launch configuration.

  .. c7n-schema:: Delete
      :module: c7n.resources.asg