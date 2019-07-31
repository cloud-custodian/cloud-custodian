Security Hub
------------

Security Hub gives a centralized dashboard of security events across data feeds from many different
tools.

Custodian supports deep integration with security hub to support the following use cases.

 - post and update findings on any resource type to security hub
   See :ref:`post-finding action <aws.common.actions.post-finding>`

 - filtering resources on the basis of extant findings
   See :ref:`finding filter <aws.common.filters.finding>`

 - lambda execution mode triggered on ingestion of security hub findings
   `mode: hub-finding`

 - lambda execution mode as a custom action in the security hub ui. Note custodian
   security hub actions work against both findings and insights.
   `mode: hub-action`


Modes
+++++

Execute a policy lambda in response to security hub finding event or action.


This policy will provision a lambda and security hub custom action.
The action can be invoked on a finding or insight result (collection
of findings). The action name will have the resource type prefixed as
custodian actions are resource specific.

.. code-block:: yaml

   policy:
     - name: remediate
       resource: aws.ec2
       mode:
         type: hub-action
         role: MyRole
       actions:
        - snapshot
        - type: set-instance-profile
          name: null
        - stop


This policy will provision a lambda that will process high alert findings from
guard duty (note custodian also has support for guard duty events directly).

.. code-block:: yaml

   policy:
     - name: remediate
       resource: aws.iam
       mode:
         type: hub-finding
	 role: MyRole
       filters:
         - type: event
           key: detail.findings[].ProductFields.aws/securityhub/ProductName
           value: GuardDuty
         - type: event
           key: detail.findings[].ProductFields.aws/securityhub/ProductName
           value: GuardDuty
       actions:
         - remove-keys

Note, for custodian we support additional resources in the finding via the Other resource,
so these modes work for resources that security hub doesn't natively support.

https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cloudwatch-events.html



