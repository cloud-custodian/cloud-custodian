.. _ec2:

Elastic Cloud Compute (EC2)
===========================

Query
-----

- Basic JMESPath Query (see :py:class:`c7n.filters.ValueFilter`)
- Valid EC2 Query Filters (see `EC2 Describe Instances <http://docs.aws.amazon.com/AWSEC2/latest/CommandLineReference/ApiReference-cmd-DescribeInstances.html>`_)

.. code-block:: json

   EC2_VALID_FILTERS = {
       'architecture': ('i386', 'x86_64'),
       'availability-zone': str,
       'iam-instance-profile.arn': str,
       'image-id': str,
       'instance-id': str,
       'instance-lifecycle': ('spot',),
       'instance-state-name': (
           'pending',
           'terminated',
           'running',
           'shutting-down',
           'stopping',
           'stopped'),
       'instance.group-id': str,
       'instance.group-name': str,
       'tag-key': str,
       'tag-value': str,
       'tag:': str,
       'vpc-id': str}

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``ebs``
  Filter based on Volumes attached to Instance

Filter by State Transition Filter
  Filter instances by state (see `Instance Lifecycle <http://goo.gl/TZH9Q5>`_)

``image-age``
  Filter on the age of the instance AMI based on the ``ImageId`` ``CreationDate``

``image``
  Filter on the ImageId of the instance

``offhour``
  Filter for
  :py:class:`c7n.resources.ec2.InstanceOffHour`

``onhour``
  Filter for
  :py:class:`c7n.resources.ec2.InstanceOnHour`

``ephemeral``
  Filter for instances that have ephemeral drives

``instance-uptime``
  Filter based on instance ``LaunchTime`` in days

``instance-age``
  Filter based on the ``AttachTime`` of the EBS Volumes in days

Actions
-------

Mark
  Tag instances with mark instances matching filters with a ``c7n_status`` tag by
  default and configurable value. Here's an example of renaming an extant tag:

  .. code-block:: yaml

     policies:
       - name: ec2-tag-instances
         resource: ec2
         filters:
           - "tag:CostCenter": foobar
         actions:
           - type: mark
             tag: CostCenter
             msg: barrum

Start
  Start a set of instances (presumably) already stopped, the start action will automatically
  filter instances to those that are already in the correct state.

  This example will restart all stopped instances.

  .. code-block:: yaml

     policies:
       - name: ec2-start
         resources: ec2
         actions:
           - start

Stop
  Will stop the instances. Stopped instances do not incur EC2 instance costs.

Terminate
  Will terminate the instances. Use with caution!

Snapshot
  Snapshots the instances' attached EBS volumes.

  This example will create snapshots for all instances and copy the Owner tag value
  from the instance to the new snapshot.

  .. code-block:: yaml

     policies:
        - name: ec2-nightly-backup
          resource: ec2
          actions:
            - type: snapshot
              copy-tags:
                - Owner
