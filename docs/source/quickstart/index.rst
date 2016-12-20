.. _quickstart:

Getting Started
===============

See also the readme in the GitHub repository.

* :ref:`install-cc`
* :ref:`explore-cc`
* :ref:`write-policy`
* :ref:`run-policy`
* :ref:`monitor-cc`

.. _install-cc:

Install Cloud Custodian
-----------------------

To install Cloud Custodian, just run::

  $ pip install c7n

.. _explore-cc:

Explore Cloud Custodian
-----------------------

* Run ``custodian -h`` to see a list of available commands.
* Run ``custodian schema`` to see the complete list of AWS resources against which you can run policies. To invoke command-line help with more information about policy schema details, run ``custodian schema -h``.
* Run ``custodian schema -<resource_name>`` to see the available filters and actions for each resource.
* Drill down to get more information about available policy settings for each resource, where the model for the command is::

  $ custodian schema <resource>.<category>.<item>

  Examples::

  $ custodian schema ebs.actions

  ::

  $ custodian schema ec2.filters.instance-age


.. _write-policy:

Write your first policy
-----------------------

A policy specifies the following items:

* The resource to run the policy against
* The resource state or states the policy checks (filters)
* The action or actions to take on the resource depending on the specified filters

For more information, see the following topics:

* :ref:`Basic concepts and terms <glossary>`
* :ref:`Example offhours policy <offhours>`
* :ref:`Example tag compliance policy <tagCompliance>`

The ``custodian schema`` commands show you the available filters and actions for each resource. For each individual item, they also provide a detailed schema. For example::

  $ custodian schema s3.filters.is-log-target

provides the following information::

  Help:
  -----
  
  Filter and return buckets are log destinations.

  Not suitable for use in lambda on large accounts, This is a api
  heavy process to detect scan all possible log sources.
  
  Sources:
    - elb (Access Log)
    - s3 (Access Log)
    - cfn (Template writes)
    - cloudtrail

  Schema:
  -------
  
  {   'additionalProperties': False,
      'properties': {   'type': {   'enum': ['is-log-target']},
                      'value': {   'type': 'boolean'}},
      'required': ['type'],
      'type': 'object'}

The policy is validated automatically when you run it, but you can also validate it separately::

  $ custodian validate -c <policy>.yml

You can also check which resources are identified by the policy, without running any actions on the resources::

  $ custodian run --dryrun -c <policy>.yml -c <output-directory>


.. _run-policy:

Run the policy
--------------

At its most basic, running a policy requires only the following command::

  $ custodian run -c <policy_file> -s <output_directory>

Custodian will create the output directory if it does not exist.

This command writes the log files to the output directory. Note that the logs are appended to any existing log files; the logs are not overwritten by default. 

.. _monitor-cc:

Monitor resources
-----------------

Additional commands let you monitor your services in detail.

You can generate metrics by specifying the boolean metrics flag::

  $ custodian run -c <policyfile>.yml -s <output_directory> --metrics

You can also upload Cloud Custodian logs to CloudWatch logs::

  $ custodian run -c <policyfile>.yml --log-group=/cloud-custodian/<dev-account>/<region>

And you can output logs and resource records to S3::

  $ custodian run -c <policyfile>.yml -s s3://<my-bucket><my-prefix>

For details, see :ref:`usage`.

