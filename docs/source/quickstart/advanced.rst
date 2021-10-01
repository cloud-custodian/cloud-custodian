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
event        In serverless, the event that triggered the policy
account      When running in c7n-org, current account info per account config file
==========   ========================================================================

If a policy is executing in a serverless mode the triggering ``event`` is available.

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
      actions:
        - delete


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

Server-Side Filters
-------------------

By default Cloud Custodian fetches all the resources on a cloud and filters on
the client side. 
In certain cases Cloud Custodian can suppport server-side filtering on certain classes of
resources. 

This might be useful if you're trying to minimize the amount of API call volume
or response time. 
These needs are usually specific to certain use cases and cloud resources.

Caution: Usage of this feature should consider trade offs as some features
such as caching might not be as effective. 

Support for Server-side filters is defined per-resource and handled in the
query block of a policy.  

In this example will use a server side policy to garbage collect EBS snapshots, the `query schema is defined
here.<https://github.com/cloud-custodian/cloud-custodian/blob/bb5dc8d5f1b2c9500e26d02630b64742dffcb432/c7n/resources/ebs.py#L134-L146>`_

Check the documentation for `the list of
filters<https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.describe_snapshots>`_,
do note, they are put in the query stanza, not the filter stanza. 

For example, this policy:

.. code-block:: yaml

  policies:
    - name: garbage-collect--snapshots
      resource: aws.ebs-snapshot
      filters:
          - type: age
            days: 7
            op: ge
          - "tag:custodian_snapshot": present
      actions:
          - delete
      
If you have a large amount of snapshots, it would be inefficent to send this
query to the client to process, so we can take advantage of some server-side
filtering to minimize traffic. 

.. code-block:: yaml

  policies:
    - name: garbage-collect-snapshots
      resource: aws.ebs-snapshot
      query:
        - Name: "tag:environment"
          Values: ["dev"]

With these changes, server-side filters make sure you only query snapshots in
the "dev" environment without needing to send the information to the client.

Now let's combine server-side and client-side filtering to create a more
efficient method of cleaning up EBS snapshots

.. code-block:: yaml

  policies:
    - name: garbage-collect-snapshots-advanced
      resource: aws.ebs-snapshot
      query:
        - Name: "tag-key"
          Values: ["custodian_snapshot"]
      filters:
        - type: age
          days: 7
          op: greater-than    
      actions:
        - delete

In this example, we are using the query block to use a server-side filter to
check the tag-key for any snapshot tagged custodian_snapshot. 
Custodian will then take those results, and apply it to the filters block, which
is executed next, this time on the client. 

For most use cases, using the client side filter is the recommendation. 
As a real example, if you have 100,000 snapshots, the server side filter can be used
to do the heavy lifting, and the client-side can then throw out all the matches
newer than 7 days. 
This is one of those use cases where using the server-side filter resulted in
improved performance and latency, however, it is strongly recommended that you
evaluate the usage of server-side filters on a case-by-case basis and not a general best practice.