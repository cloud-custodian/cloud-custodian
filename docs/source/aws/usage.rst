.. _usage:

Monitoring your environment
===========================

Cloud Custodian generates a consistent set of outputs for any given
policy.

Custodian automatically generates per policy outputs with resources metrics
and archives serialization for all resources that match against a policy's
filters.

TODO: figure out where "Custodian Dashboards in CloudWatch" page goes -- 
here? its own page? part of Getting Started?


Metrics
-------

By default Cloud Custodian generates CloudWatch metrics on each policy for
the number of resources that matched the set of filters,
the time to retrieve and filter the resources, and the time to
execute actions.

In practice this number of matching resources allows for generating
enough metrics to put together useful dashboards over policies
in CloudWatch custom dashboards.

Additionally some filters and actions may generate their own metrics.

In order to enable metrics output, the boolean metrics
flag needs to be specified when running Cloud Custodian::

  $ custodian run -s <output_directory> --metrics-enabled aws <policyfile>.yml

You can also consolidate metrics into a single account by specifying the ``master``
location in the cli. Note that this is only applicable when using the ``--assume`` option
in the cli or when using c7n-org. By default, metrics will be sent to the same account
that is being executed against::

  $ custodian run -s <output_directory> --metrics-enabled aws://master

Additionally, to use a different namespace other than the default ``CloudMaid``, you can
add the following query parameter to the metrics flag::

  $ custodian run -s <output_directory> --metrics-enabled aws://?namespace=foo

This will create a new namespace, ``foo`` in CloudWatch Metrics. You can also combine
these two options to emit metrics into a custom namespace in a central account::

  $ custodian run -s <output_directory> --metrics-enabled aws://master?namespace=foo

Finally, to send metrics to a specific region, use the ``region`` query parameter to
specify a region::

  $ custodian run -s <output_directory> --metrics-enabled aws://?region=us-west-2

When running the metrics in a centralized account or when centralizing to a specific
region, additional account and region dimensions will be included.


CloudWatch Logs
---------------

Custodian can optionally upload its logs in realtime to CloudWatch logs, if
a log group is specified. Each policy's log output is generated as a
separate stream.

Usage example::

  $ custodian run --log-group=/cloud-custodian/<dev-account>/<region> <policyfile>.yml


If enabled, it is recommended to set a log subscription on the group to
be informed of an operations issue.

If S3 output is also enabled, then it is also recommended to set a log group
archival policy and to use the S3 logs as permanent/audit archive.


S3 Logs & Records
-----------------

Custodian will output its logs and structured resource records in JSON format to S3, along
with its log files for archival purposes.

The S3 bucket and prefix can be specified via parameters::

  $ custodian run --output-dir s3://<my-bucket>/<my-prefix> <policyfile>.yml

Reports
-------

CSV or text-based reports can be generated with the ``report`` subcommand.

Reporting is used to list information gathered during previous calls to the ``run``
subcommand.  If your goal is to find out what resources match on a policy use ``run``
along with the ``--dryrun`` option.
