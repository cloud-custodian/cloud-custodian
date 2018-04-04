.. _advanced:

Advanced Usage
==============

* :ref:`run-multiple-regions`
* :ref:`report-multiple-regions`
* :ref:`report-custom-fields`
* :ref:`dry-policy`

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

.. _dry-policy:

DRY - how to remove duplication in policies
-------------------------------------------

Sometimes there are parts of your policies that you would like to reuse in other policies.
First approach would be to duplicate the old one in a new one, and edit only the differences.
However, the DRY principle (Dont't Repeat Yourself) tells us that it's better to have only one
single representation of a piece of knowledge. So we would like to prevent duplication and copy/pasting.

By default, YAML does not allow easy reuse ; however a small extension has been added to allow
policies to include other yaml files.

This way you remove redundancy and copy/paste and have a single place to edit your changes.

The syntax for this extension is ``!include my_policy_extract.yaml``. The included file
does not need to be a valid policy itself - it can be any extract or part that you want to reuse.

You can then include it in yaml policies.

E.g. : create a file named ``tag_validation.yaml`` with this content:

.. code-block:: yaml

    - or:
      - type: value
        key: tag:my_billing_tag
        op: in
        value:
          - "project1"
          - "project2"
      - type: value
        key: tag:my_billing_tag
        op: glob
        value: "project3_*"

Then create two policies that will include this tag:

.. code-block:: yaml

    vars:
      tag-filters: &tag-compliance-filters !include tag_validation.yaml

    policies:
    - name: ec2-mark
      resource: ec2
      filters:
        - State.Name: running
        - "tag:maid_status": absent
        - or:
          - "tag:my_billing_tag": absent
          - not: *tag-compliance-filters
      actions:
        - type: mark-for-op
          op: stop
          days: 7


.. code-block:: yaml

    vars:
      tag-filters: &tag-compliance-filters !include tag_validation.yaml

    policies:
    - name: asg-mark
      resource: asg
      filters:
        - SuspendedProcesses: []
        - "tag:maid_status": absent
        - or:
          - "tag:my_billing_tag": absent
          - not: *tag-compliance-filters
      actions:
        - type: mark-for-op
          op: suspend
          days: 7

    - name: asg-unmark
      resource: asg
      filters:
        - "tag:maid_status": not-null
        - "tag:my_billing_tag": present
        - and: *tag-compliance-filters
      actions:
        - unmark


You can mix and match the includes, anchors/aliases to achieve your goal
of writing clean policies.

Do not forget to use ``custodian validate`` to ensure that your policy is
properly parsed and understood.
