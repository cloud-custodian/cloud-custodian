.. _advanced:

Advanced Usage
==============

* :ref:`run-multiple-regions`
* :ref:`report-multiple-regions`
* :ref:`report-custom-fields`
* :ref:`policy_resource_limits`

.. _run-multiple-regions:

Running against multiple regions
--------------------------------

By default Cloud Custodian determines the region to run against in the following
order:

 * the ``--region`` flag
 * the ``AWS_DEFAULT_REGION`` environment variable
 * the region set in the ``~/.aws/config`` file

It is possible to run policies against multiple regions by specifying the ``--region``
flag multiple times::

  custodian run -s out --region us-east-1 --region us-west-1 policy.yml

If a supplied region does not support the resource for a given policy that region will
be skipped.

The special ``all`` keyword can be used in place of a region to specify the policy
should run against `all applicable regions
<https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/>`_
for the policy's resource::

  custodian run -s out --region all policy.yml

Note: when running reports against multiple regions the output is placed in a different
directory than when running against a single region.  See the multi-region reporting
section below.

.. _report-multiple-regions:

Reporting against multiple regions
----------------------------------

When running against multiple regions the output files are placed in a different
location that when running against a single region.  When generating a report, specify
multiple regions the same way as with the ``run`` command::

   custodian report -s out --region us-east-1 --region-us-west-1 policy.yml

A region column will be added to reports generated that include multiple regions to
indicate which region each row is from.

.. _scheduling-policy-execution:


Conditional Policy Execution
----------------------------

Cloud Custodian can skip policies that are included in a policy file when running if
the policy specifies conditions that aren't met by the current environment.


The available environment keys are


==========   ========================================================================
Key          Description
==========   ========================================================================
name         Name of the policy
region       Region the policy is being evaluated in.
resource     The resource type of the policy.
account_id   The account id (subscription, project) the policy is being evaluated in.
provider     The name of the cloud provider (aws, azure, gcp, etc)
policy       The policy data as structure
now          The current time
account      When running in c7n-org, current account info per account config file
==========   ========================================================================


As an example, one can set up policy conditions to only execute between a given
set of dates.

.. code-block:: yaml


  policies:

    # other compliance related policies that
    # should always be running...

    - name: holiday-break-stop
      description: |
        This policy will stop all EC2 instances
        if the current date is between  12-15-2018
        to 12-31-2018 when the policy is run.

        Use this in conjunction with a cron job
        to ensure that the environment is fully
        turned off during the break.
      resource: ec2
      conditions:
         - type: value
           key: now
           op: greater-than
           value_type: date
           value: "2018-12-15"
         - type: value
           key: now
           op: less-than
           value_type: date
           value: "2018-12-31"
      filters:
        - "tag:holiday-off-hours": present
      actions:
        - stop

    - name: holiday-break-start
      description: |
        This policy will start up all EC2 instances
        and only run on 1-1-2019.
      resource: ec2
      conditions:
        - type: value
          key: now
          value_type: date
          op: greater-than
          value: "2009-1-1"
        - type: value
          key: now
          value_type: date
          op: less-than
          value: "2019-1-1 23:59:59"
      filters:
        - "tag:holiday-off-hours": present
      actions:
        - start


If a policy is executing in a serverless mode, the above environment keys
are evaluated *during the deployment* of the policy using ``type: value``
conditions (any ``type: event`` conditions are skipped).  The *execution*
of the policy will evaluate these again, but will also include the
triggering ``event``.  These events can be evaluated using a ``type:
event`` condition.  This is useful for cases where you have a more complex
condition than can be handled by an event ``pattern`` expression, but you
want to short-circuit the execution before it queries the resources.

For instance, the below example will only deploy the policy to the
``us-west-2`` and ``us-east-2`` regions.  The policy will stop execution
before querying any resources if the event looks like it was created by a
service or automation identity matching a complex regular expression.

.. code-block:: yaml

  policies:
    - name: ec2-auto-tag-creator
      description: Auto-tag Creator on EC2 if not set.
      resource: aws.ec2
      mode:
        type: cloudtrail
        events:
         - RunInstances
      conditions:
        - type: value           ─▶ evaluated at deployment and execution
          key: region
          op: in
          value:
            - us-east-2
            - us-west-2
        - not:
          - type: event         ─▶ evaluated at execution only
            key: "detail.userIdentity.arn"
            op: regex-case
            value: '.*(CloudCustodian|Jenkins|AWS.*ServiceRole|LambdaFunction|\/sfr-|\/i-|\d{8,}$)'
      filters:
        - "tag:Creator": empty
      actions:
        - type: auto-tag-user
          tag: Creator



.. _policy_resource_limits:

Limiting how many resources custodian affects
---------------------------------------------

Custodian by default will operate on as many resources exist within an
environment that match a policy's filters. Custodian also allows policy
authors to stop policy execution if a policy affects more resources than
expected, either as a number of resources or as a percentage of total extant
resources.

.. code-block:: yaml

  policies:

    - name: log-delete
      description: |
        This policy will delete all log groups
        that haven't been written to in 5 days.

        As a safety belt, it will stop execution
        if the number of log groups that would
        be affected is more than 5% of the total
        log groups in the account's region.
      resource: aws.log-group
      max-resources-percent: 5
      filters:
        - type: last-write
          days: 5


Max resources can also be specified as an absolute number using
`max-resources` specified on a policy. When executing if the limit
is exceeded, policy execution is stopped before taking any actions::

  custodian run -s out policy.yml
  custodian.commands:ERROR policy: log-delete exceeded resource limit: 2.5% found: 1 total: 1

If metrics are being published :code:`(-m/--metrics)` then an additional
metric named `ResourceCount` will be published with the number
of resources that matched the policy.

Max resources can also be specified as an object with an `or` or `and` operator
if you would like both a resource percent and a resource amount enforced.


.. code-block:: yaml

  policies:

    - name: log-delete
      description: |
        This policy will not execute if
        the resources affected are over 50% of
        the total resource type amount and that
        amount is over 20.
      resource: aws.log-group
      max-resources:
        percent: 50
        amount: 20
        op: and
      filters:
        - type: last-write
          days: 5
      actions:
        - delete


.. _report-custom-fields:

Adding custom fields to reports
-------------------------------

Reports use a default set of fields that are resource-specific.  To add other fields
use the ``--field`` flag, which can be supplied multiple times.  The syntax is:
``--field KEY=VALUE`` where KEY is the header name (what will print at the top of
the column) and the VALUE is a JMESPath expression accessing the desired data::

  custodian report -s out --field Image=ImageId policy.yml

If hyphens or other special characters are present in the JMESPath it may require
quoting, e.g.::

  custodian report -s . --field "AccessKey1LastRotated"='"c7n:credential-report".access_keys[0].last_rotated' policy.yml

To remove the default fields and only add the desired ones, the ``--no-default-fields``
flag can be specified and then specific fields can be added in, e.g.::

  custodian report -s out --no-default-fields --field Image=ImageId policy.yml
