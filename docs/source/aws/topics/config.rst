
AWS Config
----------


Custodian has deep integration with config, a custodian policy:

- Can be deployed as config-rule for any resource type supported by config.

- Can use config as resource database instead of querying service
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

When the resources is supported you will get this validation error::

  custodian.commands:ERROR Policy: kinesis-one-stream is invalid: resource:aws.kinesis fully supported by config and should use mode: config-rule
