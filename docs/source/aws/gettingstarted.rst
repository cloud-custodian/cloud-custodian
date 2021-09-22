.. _aws-gettingstarted:

Getting Started
===============

.. _aws-write-policy:

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
        resource: aws.ec2
        filters:
          - "tag:Custodian": present

At this point, we have specified the following things:

1. The name of the policy
2. The resource type to query against, in this case (aws.ec2)
3. The filters list
4. The Custodian tag filter

Running this policy will not execute any actions as the actions list does not exist.

We can extend this example to stop the instances that are actually filtered in by the
Custodian tag filter by simply specifying the ``stop`` action:

.. code-block:: yaml

    policies:
      - name: my-first-policy
        resource: aws.ec2
        filters:
          - "tag:Custodian": present
        actions:
          - stop

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


See our extended example of a policy's structure
:ref:`tag compliance policy <policyStructure>`, or browse all of our
:ref:`use case recipes <usecases>`.


A 2nd Example Policy
--------------------

First a role must be created with the appropriate permissions for
custodian to act on the resources described in the policies yaml
given as an example below. For convenience, an `example policy <../_static/custodian-quickstart-policy.json>`_
is provided for this quick start guide. Customized AWS IAM policies
will be necessary for your own custodian policies

To implement the policy:

#. Open the AWS console
#. Navigate to IAM -> Policies
#. Use the json option to copy the `example policy <../_static/custodian-quickstart-policy.json>`_ as a new AWS IAM Policy
#. Name the IAM policy as something recognizable and save it.
#. Navigate to IAM -> Roles and create a role called CloudCustodian-QuickStart
#. Assign the role the IAM policy created above.
#. Now with the pre-requisite completed; you are ready continue and run custodian.

A custodian policy file needs to be created in YAML format, as an example

.. code-block:: yaml

  policies:
  - name: s3-cross-account
    description: |
      Checks S3 for buckets with cross-account access and
      removes the cross-account access.
    resource: s3
    region: us-east-1
    filters:
      - type: cross-account
    actions:
      - type: remove-statements
        statement_ids: matched

  - name: ec2-require-non-public-and-encrypted-volumes
    resource: aws.ec2
    description: |
      Provision a lambda and cloud watch event target
      that looks at all new instances and terminates those with
      unencrypted volumes.
    mode:
      type: cloudtrail
      role: CloudCustodian-QuickStart
      events:
        - RunInstances
    filters:
      - type: ebs
        key: Encrypted
        value: false
    actions:
      - terminate

  - name: tag-compliance
    resource: aws.ec2
    description: |
      Schedule a resource that does not meet tag compliance policies
      to be stopped in four days.
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - "tag:AppId": absent
      - or:
        - "tag:OwnerContact": absent
        - "tag:DeptID": absent
    actions:
      - type: mark-for-op
        op: stop
        days: 4


Given that, you can run Cloud Custodian with

.. code-block:: bash

  # Validate the configuration (note this happens by default on run)
  custodian validate policy.yml

  # Dryrun on the policies (no actions executed) to see what resources
  # match each policy.
  custodian run --dryrun -s out policy.yml

  # Run the policy
  custodian run -s out policy.yml

.. _monitor-aws-cc:

Monitor AWS
-----------

You can generate CloudWatch metrics by specifying the ``--metrics`` flag and specifying ``aws``::

  custodian run -s <output_directory> --metrics aws <policyfile>.yml

You can also upload Cloud Custodian logs to CloudWatch logs::

  custodian run --log-group=/cloud-custodian/<dev-account>/<region> -s <output_directory> <policyfile>.yml

And you can output logs and resource records to S3::

  custodian run -s s3://<my-bucket><my-prefix> <policyfile>.yml

If Custodian is being run without Assume Roles, all output will be put into the same account.
Custodian is built with the ability to be run from different accounts and leverage STS
Role Assumption for cross-account access. Users can leverage the metrics that are
being generated after each run by creating Custodian Dashboards in CloudWatch.

Troubleshooting & Tinkering
+++++++++++++++++++++++++++

If you are not using the ``us-east-1`` region, then you'll need to specify that
as well, either on the command line or in an environment variable:

.. code-block:: bash

    --region=us-west-1

.. code-block:: bash

  AWS_DEFAULT_REGION=us-west-1
