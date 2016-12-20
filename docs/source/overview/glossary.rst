.. _glossary:

Basic concepts and terms
========================

Cloud Custodian works with the following basic concepts, terms, and relationships between them.

Policy - :py:class:`c7n.policy`
  Defined in yaml, specifies a set of filters and actions to take
  on a given AWS resource type.

Resource - :py:class:`c7n.manager.ResourceManager`
  Provides for retrieval of a resource of a given type (typically via AWS API)
  and defines the vocabulary of filters and actions that can be used on those
  resources (e.g., ASG, S3, EC2, ELBs, etc).

Mode - :py:class:`c7n.policy` (yes, ``policy``)
  Defines how the policy will execute (lambda, config rule, poll, etc).

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
       value: "Unencrypted EBS! Please recreate with Encryption"
     - type: terminate
       force: true
