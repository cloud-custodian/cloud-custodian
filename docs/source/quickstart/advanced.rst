.. _advanced:

Advanced Usage
==============

* :ref:`run-multiple-regions`
* :ref:`report-multiple-regions`
* :ref:`report-custom-fields`

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

  $ custodian run -s out --region us-east-1 --region us-west-1 policy.yml

If a supplied region does not support the resource for a given policy that region will
be skipped.

The special ``all`` keyword can be used in place of a region to specify the policy
should run against `all applicable regions
<https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/>`_
for the policy's resource::

  $ custodian run -s out --region all policy.yml

Note: when running reports against multiple regions the output is placed in a different
directory than when running against a single region.  See the multi-region reporting
section below.

.. _report-multiple-regions:

Reporting against multiple regions
----------------------------------

When running against multiple regions the output files are placed in a different
location that when running against a single region.  When generating a report, specify
multiple regions the same way as with the ``run`` command::

   $ custodian report -s out --region us-east-1 --region-us-west-1 policy.yml

A region column will be added to reports generated that include multiple regions to
indicate which region each row is from.

.. _scheduling-policy-execution:

Filtering Policy Execution by Date
----------------------------------

Cloud Custodian can skip policies that are included in a policy file when running if
the start and end date/times are before or after the current date-time respectively.
To utilize this behavior, include the ``start``, ``end``, and ``tz`` attributes
in the policy.

If the current date and/or time is after the ``start``  value and there is no ``end``
value, the policy will execute. Likewise, if the ``end`` value is after the current
date and/or time and there is no ``start`` value, the policy will execute. Otherwise,
the current date and/or time must fall between ``start`` and ``end`` values for the
policy to execute. In order to specify a timezone, a ``tz`` attribute must be
specified. Otherwise, UTC will be used to perform the comparison.

This allows you to continuously run the same policy file for different time periods,
without having to update the policy file for specific days or times.

**Note**: Dates and/or times specified in ``start`` or ``end`` must not be offset-aware.
The policy's ``tz`` attribute will be applied to the ``start`` and ``end`` values.
If no ``tz`` attribute is specified, UTC is set by default.

``start`` and ``end`` attributes support the following formats:

* a date (example: ``1-1-2018``, ``January 1 2018``, ``2018-1-1``)
* a offset-naive time with up to second precision (example: ``2:03:01 PM`` ``16:03:01``, ``3 AM``)
* a date and a offset-naive time with up to second precision (example: ``1-1-2018 2 PM``, ``January 1 2018 14:00:00``)

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
      start: "2018-12-15"
      end: "2018-12-31"
      tz: UTC
      filters:
        - "tag:holiday-off-hours": present
      actions:
        - stop

    - name: holiday-break-start
      description: |
        This policy will start up all EC2 instances
        and only run on 1-1-2019.
      resource: ec2
      start: "2019-1-1"
      end: "2019-1-1 23:59:59"
      tz: UTC
      filters:
        - "tag:holiday-off-hours": present
      actions:
        - start


.. _report-custom-fields:

Adding custom fields to reports
-------------------------------

Reports use a default set of fields that are resource-specific.  To add other fields
use the ``--field`` flag, which can be supplied multiple times.  The syntax is:
``--field KEY=VALUE`` where KEY is the header name (what will print at the top of
the column) and the VALUE is a JMESPath expression accessing the desired data::

  $ custodian report -s out --field Image=ImageId policy.yml

If hyphens or other special characters are present in the JMESPath it may require
quoting, e.g.::

  $ custodian report -s . --field "AccessKey1LastRotated"='"c7n:credential-report".access_keys[0].last_rotated' policy.yml

To remove the default fields and only add the desired ones, the ``--no-default-fields``
flag can be specified and then specific fields can be added in, e.g.::

  $ custodian report -s out --no-default-fields --field Image=ImageId policy.yml
