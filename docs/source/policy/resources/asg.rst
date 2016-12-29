.. _asg:

Auto Scaling Groups (ASG)
=========================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

Actions
-------

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
  :py:class:``c7n.offhours``

  .. c7n-schema:: OffHour
      :module: c7n.resources.asg

``onhour`` or ``onhour``
  Turn resources on based on a schedule.
  :py:class:``c7n.offhours``

  .. c7n-schema:: OnHour
      :module: c7n.resources.asg
