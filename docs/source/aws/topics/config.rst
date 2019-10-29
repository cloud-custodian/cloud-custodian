
AWS Config
----------


Custodian has deep integration with config, a custodian policy:

- Can be deployed as config-rule.

- Can use config as resource database instead of. Custodian supports
  querying resources with Config's SQL expression language.

- Can filter resources based on their compliance with one or more config rules.


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
      resource: aws.dynamodb
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


