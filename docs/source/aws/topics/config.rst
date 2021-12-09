
AWS Config
----------


Custodian has deep integration with config, a custodian policy:

- Can be deployed as an AWS Config custom rule (config-rule mode) for any resource type supported by config.

- Can be deployed as an AWS Config managed rule (config-managed-rule mode).

- Can use AWS Config as resource database instead of querying service
  describe apis. Custodian supports server side querying resources
  with Config's SQL expression language.

- Can filter resources based on their compliance with one or more config rules.

- Can be deployed as a config-poll-rule against any resource type supported
  by cloudformation.

Custodian does the legwork of normalizing the resource description
from config's idiosyncratic format to one that looks like describe api
call output, so policies can utilize config with a simple change of source
or execution mode.


Config Source
+++++++++++++

You can use config as a cmdb of resources instead of doing describes
by adding source: config to any policy on a resource type that config
supports. This also supports doing arbitrary sql selects (via config's
select resources api) on the resources in addition to the standard
custodian filters.

.. code-block:: yaml

  policies:
    - name: dynamdb-checker
      resource: aws.dynamodb-table
      source: config
      query:
        - clause: "resourceId = 'MyTable'"
      filters:
        - SSEDescription: absent


Config Rule
+++++++++++

Custodian is also one of the easiest ways of authoring custom config
rules. For any config supported resource, you can just add a mode with
type:config-rule to have the policy deployed as a custom config rule
lambda.

.. code-block:: yaml

  policies:
    - name: ec2-checker
      resource: aws.ec2
      mode:
        type: config-rule
        role: MyLambdaConfigRole
      filters:
        - type: image
          tag: "NotSupported"
	  value: absent


Filter
++++++

Custodian also supports filtering resources based on their compliance
with other config-rules.

.. code-block:: yaml

   policies:
     - name: ec2-remediate-non-compliant
       resource: aws.ec2
       filters:
         - type: config-compliance
           rules: [my_other_config_rule, some_other_rule]
           states: [NON_COMPLIANT]
       actions:
         - stop


Config Poll Rule
++++++++++++++++

For resources not supported natively by AWS Config, an execution mode
of type: config-poll-rule can be used for any resource supported by
CloudFormation.  This is effectively a periodic policy that queries
the resource's service api and filters resources to evaluate
compliance/non-compliance and then records results to AWS Config.
CloudFormation resources are only partially supported by AWS Config,
and are not supported for `source: config` nor do they support resource
timeline or resource attributes.

.. code-block:: yaml

   policies:
     - name: kinesis-one-stream
       resource: aws.kinesis
       mode:
         type: config-poll-rule
	 role: custodian-config-role
         schedule: Three_Hours
       filters:
         - tag:App: Dev

Config Managed Rule
++++++++++++++++

AWS Config provides AWS managed rules, which are predefined, customizable
rules that AWS Config uses to evaluate whether your AWS resources comply
with common best practices. Additionally, these managed rules can be
associated with predefined remediation SSM actions so that violated resources
can be remediated.

For a list of managed rules, refer to: https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html

Using config-managed-rule policy mode, you can tell AWS Config to activate a
particular managed rule. You can also configure various properties to configure
the rule and the remediation process.

Example of such policy

.. code-block:: yaml

  policies:
    - name: config-managed-s3-bucket-public-write-remediate-event
      description: |
        This policy detects if S3 bucket allows public write by the bucket policy or ACL and remediates.
      comment: |
        This policy detects if S3 bucket policy or ACL allows public write access.
        When the bucket is evaluated as 'NON_COMPLIANT', the action 'AWS-DisableS3BucketPublicReadWrite' is triggered and remediates.
      resource: config-rule

      mode:
        type: config-managed-rule
        rule_id: S3_BUCKET_PUBLIC_WRITE_PROHIBITED
        rule_prefix: 'custodian-'
        resource_types:
          - 'AWS::S3::Bucket'
        rule_parameters: '{}'
        remediation:
          target_id: AWS-DisableS3BucketPublicReadWrite
          automatic: true
          maximum_automatic_attempts: 4
          parameters:
            AutomationAssumeRole:
              StaticValue:
                Values:
                  - 'arn:aws:iam::{account_id}:role/my-role'
            S3BucketName:
              ResourceValue:
                Value: RESOURCE_ID

The properties of the config-managed-rule mode roughly corresponds to the
AWS Config rule and remediation API properties, refer to the correspoding
API doc for more information:

- https://docs.aws.amazon.com/config/latest/APIReference/API_PutConfigRule.html

- https://docs.aws.amazon.com/config/latest/APIReference/API_PutRemediationConfigurations.html
