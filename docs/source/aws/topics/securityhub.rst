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

Additional details from the initial integration of security hub.
https://aws.amazon.com/blogs/opensource/announcing-cloud-custodian-integration-aws-security-hub/
