.. _quickstart:

Getting Started
===============

See also the readme in the GitHub repository.

* :ref:`install-cc`
* :ref:`write-policy`
* :ref:`explore-cc`
* :ref:`monitor-cc`
* :ref:`tab-completion`

.. _install-cc:

Install Cloud Custodian
-----------------------

To install Cloud Custodian, just run::

  $ virtualenv --python=python2 custodian
  $ source custodian/bin/activate
  (custodian) $ pip install c7n

(Note that Custodian's `Lambda features <../policy/lambda.html>`_ currently `do
not work <https://github.com/capitalone/cloud-custodian/issues/193>`_ outside
of a virtualenv.)


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

    AWS_ACCESS_KEY_ID="foo" AWS_SECRET_ACCESS_KEY="bar" custodian run --output-dir=. custodian.yml

Note: If you already have AWS credentials configured for AWS CLI or SDK access, then you may omit providing them on the command line. 
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
<glossary>`. See our extended example of a policy's structure 
:ref:`tag compliance policy <policyStructure>`, or browse all of our
:ref:`use case recipes <usecases>`.

Troubleshooting & Tinkering
+++++++++++++++++++++++++++

If you are not using the ``us-east-1`` region, then you'll need to specify that
as well, either on the command line or in an environment variable:

.. code-block:: bash

    --region=us-west-1

.. code-block:: bash

  $ AWS_DEFAULT_REGION=us-west-1


The policy is validated automatically when you run it, but you can also
validate it separately:

.. code-block:: bash

  $ custodian validate custodian.yml

You can also check which resources are identified by the policy, without
running any actions on the resources:

.. code-block:: bash

  $ custodian run --dryrun -s . custodian.yml


.. _explore-cc:

Explore Cloud Custodian
-----------------------

Run ``custodian -h`` to see a list of available commands.

Run ``custodian schema`` to see the complete list of AWS resources against
which you can run policies. To invoke command-line help with more information
about policy schema details, run ``custodian schema -h``.

Run ``custodian schema <cloud-provider>`` to see the available resources for a specific
cloud provider: ``custodian schema aws``

Run ``custodian schema <resource>`` to see the available :ref:`filters and
actions <policy>` for each resource.

Drill down to get more information about available policy settings for each
resource, where the model for the command is::

  $ custodian schema <resource>.<category>.<item>

For example::

  $ custodian schema s3.filters.is-log-target

provides the following information::

  Help
  ----

  Filter and return buckets are log destinations.

  Not suitable for use in lambda on large accounts, This is a api
  heavy process to detect scan all possible log sources.

  Sources:
    - elb (Access Log)
    - s3 (Access Log)
    - cfn (Template writes)
    - cloudtrail

  :example:

      .. code-block: yaml

          policies:
            - name: s3-log-bucket
              resource: s3
              filters:
                - type: is-log-target

  Schema
  ------
  
  {   'additionalProperties': False,
      'properties': {   'type': {   'enum': ['is-log-target']},
                        'value': {   'type': 'boolean'}},
      'required': ['type'],
      'type': 'object'}


.. _monitor-cc:

Monitor resources
-----------------

Additional commands let you monitor your services in detail.

You can generate metrics by specifying the boolean metrics flag::

  $ custodian run -s <output_directory> --metrics <policyfile>.yml

You can also upload Cloud Custodian logs to CloudWatch logs::

  $ custodian run --log-group=/cloud-custodian/<dev-account>/<region> -s <output_directory> <policyfile>.yml

And you can output logs and resource records to S3::

  $ custodian run -s s3://<my-bucket><my-prefix> <policyfile>.yml

For details, see :ref:`usage`.

.. _tab-completion:

Tab Completion
--------------

To enable command-line tab completion for `custodian` on bash do the following one-time steps:

Run:

.. code-block:: bash

    activate-global-python-argcomplete

Now launch a new shell (or refresh your bash environment by sourcing the appropriate
file).

Troubleshooting
+++++++++++++++

If you get an error about "complete -D" not being supported, you need to update bash.
See the "Base Version Compatability" note `in the argcomplete docs
<https://argcomplete.readthedocs.io/en/latest/#global-completion>`_:

If you have other errors, or for tcsh support, see `the argcomplete docs
<https://argcomplete.readthedocs.io/en/latest/#activating-global-completion>`_.

If you are invoking `custodian` via the `python` executable tab completion will not work.
You must invoke `custodian` directly.
