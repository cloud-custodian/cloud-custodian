.. _ec2:

Elastic Cloud Compute (EC2)
===========================

Query
-----

- Basic JMESPath Query (see :py:class:`c7n.filters.ValueFilter`)
- Valid EC2 Query Filters (see `EC2 Describe Instances <http://docs.aws.amazon.com/AWSEC2/latest/CommandLineReference/ApiReference-cmd-DescribeInstances.html>`_)

.. code-block:: python

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
       'tenancy': ('dedicated', 'default', 'host'),
       'vpc-id': str}

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``ebs``
  Filter based on Volumes attached to Instance

Filter by State Transition Filter
  Filter instances by state (see `Instance Lifecycle <http://goo.gl/TZH9Q5>`_)

  .. c7n-schema:: aws.ec2.filters.ebs

``image-age``
  Filter on the age of the instance AMI based on the ``ImageId`` ``CreationDate``

  **Deprecated** use image filter with `value_type: age`

  .. c7n-schema:: aws.ec2.filters.image-age


``image``
  Filter on the ImageId of the instance

  .. c7n-schema:: aws.ec2.filters.image


``offhour``
  Filter for
  :py:class:`c7n.resources.ec2.InstanceOffHour`

  .. c7n-schema:: aws.ec2.filters.offhour


``onhour``
  Filter for
  :py:class:`c7n.resources.ec2.InstanceOnHour`

  .. c7n-schema:: aws.ec2.filters.onhour


``ephemeral``
  Filter for instances that have ephemeral drives

  .. c7n-schema:: aws.ec2.filters.ephemeral


``instance-uptime``
  Filter based on instance ``LaunchTime`` in days

  .. c7n-schema:: aws.ec2.filters.instance-uptime


``instance-age``
  Filter based on the ``AttachTime`` of the EBS Volumes in days

  .. c7n-schema:: aws.ec2.filters.instance-age


``termination-protected``
  Filter based on the ``disableApiTermination`` instance attribute.

  .. c7n-schema:: aws.ec2.filters.termination-protected


``user-data``
  Filter for EC2's with user data matching the value given.

  .. c7n-schema:: aws.ec2.filters.user-data



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

  .. c7n-schema:: aws.ec2.actions.start


  This example will restart all stopped instances.

  .. code-block:: yaml

     policies:
       - name: ec2-start
         resources: ec2
         actions:
           - start

Stop
  Will stop the instances. Stopped instances do not incur EC2 instance costs.

  .. c7n-schema:: aws.ec2.actions.stop


Terminate
  Will terminate the instances. Use with caution!

  .. c7n-schema:: aws.ec2.actions.terminate


Snapshot
  Snapshots the instances' attached EBS volumes.

  .. c7n-schema:: aws.ec2.actions.snapshot


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

PropagateSpotTags
  In case the EC2 instance is a Spot Instance, created by a Spot Instance Request,
  this action will propagate all (or a subset) of the Tags that are attached to the
  original Spot Instance Request.
  Spot Instance Request do not propagate their tags to the Spot Instances.
  (see `Tagging Spot Instance Requests <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-requests.html#concepts-spot-instances-request-tags>`_)

  However, Spot Fleets are said to propagate their Tags. (see `Tag Your Spot Fleet EC2 Instances <https://aws.amazon.com/about-aws/whats-new/2017/07/tag-your-spot-fleet-ec2-instances/>`_)

  .. c7n-schema:: aws.ec2.actions.propagate-spot-tags


  This example will copy the Name and the BillingTag tag values from the Spot Instance Request
  to the pending EC2 instances (only if they are Spot Instances)

  .. code-block: yaml
      policies:
        - name: ec2-spot-instances
          resource: ec2
        filters:
          - State.Name: pending
          - instanceLifecycle: spot
        actions:
          - type: propagate-spot-tags
            only_tags:
              - Name
              - BillingTag
