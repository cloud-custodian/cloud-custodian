.. _policy:

Policy
------

Sample Policy
=============

In this sample policy we are querying for only running EC2
instances. Based on the list that comes back we are then filtering for EC2
instances that are: not part of an Auto Scaling Group (ASG), not
already marked for an operation, have less than 10 tags, and are missing one or more
of the required tags. Once Custodian has filtered the list, it will
mark all EC2 instances that match the above criteria with a tag. That tag specifies an action
that will take place at a certain time. This policy is one of three that
are needed to manage tag compliance. The other two policies in this set are, 1)
checking to see if the tags have been corrected before the four day period
is up, and 2) performing the operation of stopping all instances
with the status to be stopped on that particular day.

.. code-block:: yaml
   :linenos:

   - name: ec2-tag-compliance-mark
     resource: ec2
     comment: |
       Mark non-compliant, Non-ASG EC2 instances with stoppage in 4 days
     query:
       - instance-state-name: running ──▶ Only apply filter to running instances
     filters:
   ▣──────  - "tag:aws:autoscaling:groupName": absent
   │▣─────  - "tag:c7n_status": absent
   │ │ ▣─── - type: tag-count
   │ │ │    - or:                           ─┐
   │ │ │      - "tag:Owner": absent          ├─If any of these tags are
   │ │ │      - "tag:CostCenter": absent     │ missing, then select instance
   │ │ │      - "tag:Project": absent       ─┘
   │ │ │
   │ │ │  actions: ─────────────────▶ For selected instances, run this action
   │ │ │    - type: mark-for-op ────▶ Mark instance for operation
   │ │ │      op: stop ─────────────▶ Stop instance
   │ │ │      days: 4 ──────────────▶ After 4 days
   │ │ │
   │ │ ▣────▶ If instance has 10 tags, skip
   │ ▣──────▶ If instance already has a c7n_status, skip
   ▣────────▶ If instance is part of an ASG, skip


Terms
=====

Policy - :py:class:`c7n.policy`
  Defined in yaml, specifies a set of filters and actions to take
  on a given AWS resource type.

Resource - :py:class:`c7n.manager.ResourceManager`
  Provides for retrieval of a resources of a given type (typically via AWS API)
  and defines the vocabulary of filters and actions that can be used on those
  resource (e.g., ASG, S3, EC2, ELBs, etc).

Mode
  Provides for retrieval of a resources of a given type (typically via AWS API) and defines the vocabulary of filters and actions that can be used on those resource. Example resource types are Auto Scaling Groups, S3 buckets, EC2 instances, Elastic Load Balancers, etc).

.. code-block:: yaml

   mode:
     type: cloudtrail
     events:
       - RunInstances

Filters - :py:class:`c7n.filters`
  Given a set of resources, how we filter to the subset that we're
  interested in operating on. The :ref:`filtering language<filters>` has some
  default behaviors across resource types like value filtering with JMESPath
  expressions against the JSON representation of a resource, as well as
  specific filters for particular resources types (instance age,
  tag count, etc).

.. code-block:: yaml

   filters:
     - "tag:aws:autoscaling:groupName": absent
     - type: ebs
       key: Encrypted
       value: false
       skip-devices:
         - "/dev/sda1"
         - "/dev/xvda"
     - type: event
       key: "detail.userIdentity.sessionContext.sessionIssuer.userName"
       value: "SuperUser"
       op: ne

Actions - :py:class:`c7n.actions`
  A verb to use on a given resource, i.e. stop, start, suspend,
  delete, encrypt, etc.

.. code-block:: yaml

   actions:
     - type: tag
       key: c7n_status
       value: "Unencrypted EBS! Please recreate with Encryption)"
     - type: terminate
       force: true


Real-time Policies
==================
  .. toctree::

     lambda
     mu

Filters
=======
  .. toctree::

     filters
     usage

Resources and Actions
=====================
.. toctree::
  :maxdepth: 2
  :titlesonly:
  :glob:

  resources/*
