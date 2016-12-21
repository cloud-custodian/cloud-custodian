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


.. _write-policy:

Write your first policy
-----------------------

A policy specifies the following items:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

For this tutorial, let's stop all EC2 instances that are tagged with
``Custodian``. To get started, go make an EC2 instance in your `AWS console
<https://console.aws.amazon.com/>`_, and tag it with the key ``Custodian`` (any
value).  Also, make sure you have an access key handy.

Then, create a file named ``custodian.yml`` with this content:

.. code-block:: yaml

    policies:
      - name: my-first-policy
        resource: ec2
        filters:
          - "tag:Custodian": present
        actions:
          - stop

.. _run-policy:

Run your policy
---------------

Now, run Custodian:

.. code-block:: bash

    AWS_ACCESS_KEY_ID="foo" AWS_SECRET_ACCESS_KEY="bar" custodian run --output=. --config=custodian.yml

If you are not using the ``us-east-1`` region, then you'll need to specify that as well, like so:

.. code-block:: bash

    --region=us-west-1

If successful, you should see output similar to the following on the command line::

    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: ec2 region:us-east-1 c7n:0.8.21.2
    2016-12-20 08:35:07,514: custodian.resources.ec2:INFO Filtered from 3 to 1 ec2
    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:ec2 has count:1 time:1.38
    2016-12-20 08:35:07,515: custodian.actions:INFO Stop 1 of 1 instances
    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: stop resources: 1 execution_time: 0.67

You should also find a new ``my-first-policy`` directory with a log and other
files (subsequent runs will append to the log by default rather than
overwriting it). Lastly, you should find the instance stopping or stopped in
your AWS console. Congratulations, and welcome to Custodian!

For more information on basic concepts and terms, check the :ref:`glossary
<glossary>`. See our extended examples of an :ref:`offhours policy <offhours>`
and a :ref:`tag compliance policy <tagCompliance>`, or browse all of our
:ref:`use case recipes <usecases>`.


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

