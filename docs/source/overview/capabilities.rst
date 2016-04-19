Capabilities
------------

Custodian currently provides policy definition around the following
AWS resources:

- :ref:`ami`
- :ref:`asg`
- :ref:`cfn`
- :ref:`ebs`
- :ref:`ec2`
- :ref:`elb`
- :ref:`kms`
- :ref:`rds`
- :ref:`redshift`
- :ref:`s3`

Custodian uses a flexible query language for filtering resources to a
particular subset that allows for compound querying. This essentially allows you
to filter for things like instances with EBS volumes that are not set to delete
on instance termination or stopped instances. This filtering can take into
account external data sources. It also provides for resource specific actions
around deletion, stopping, starting, encryption, tagging, etc.

The stateless design of Custodian greatly simplifies feature development
and operations. It also provides flexibility around execution environment (local cli,
server, lambda).

When a user runs Custodian, Custodian will run the specified policy against the account
and region specified by the user. Custodian will iterate over all resources
defined in the policy. In the CLI, users specify the account and region they want
to target. During the run, each policy in the config will generate metrics that
are sent to CloudWatch in the account that is targeted. The run will also
generate structured record output and logs that will be sent to an S3 Bucket and
CloudWatch Log Groups in the account Custodian was run from. If Custodian is being
run without Assume Roles, all output will be put into the same account. Custodian
is built with the ability to be run from different accounts and leverage STS
Role Assumption for cross-account access. Users can leverage the metrics that are
being generated after each run by creating Custodian Dashboards in CloudWatch.
