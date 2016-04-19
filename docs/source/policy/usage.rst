.. _usage:

Usage
=====

Offhours
--------

.. automodule:: c7n.offhours


Outputs
-------

Cloud Custodian generates a consistent set of outputs for any given
policy.

Custodian automatically generates per policy outputs with resources metrics
and archives serialization for all resources that match against a policy's
filters.


Metrics
#######

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

  $ cloud-custodian run -c config.yml --metrics


CloudWatch Logs
###############

Custodian can optionally upload its logs in realtime to CloudWatch logs, if
a log group is specified. Each policy's log output is generated as a
separate stream.

Usage example::

  $ cloud-custodian run -c config.yml --log-group=/cloud-custodian/dev-account/us-east-1


If enabled, it is recommended to set a log subscription on the group to
be informed of an operations issue.

If S3 output is also enabled, then it is also recommended to set a log group
archival policy and to use the S3 logs as permanent/audit archive.


S3 Logs & Records
#################

Custodian will output its logs and structured resource records in JSON format to S3, along
with its log files for archival purposes.

The S3 bucket and prefix can be specified via parameters::

  $ cloud-custodian run -c config.yml --output-dir s3://my-bucket/my/prefix

CSV reports can be generated with the ``report`` subcommand.
