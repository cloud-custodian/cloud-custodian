.. _securitygroupsdetectremediate:

Security Groups - Detect and Remediate Violations
=================================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a user creates or modifies a security group. This provides near real-time
auto-remediation action (typically within a minute) of the security group change.
Having such a quick auto-remediation action greatly reduces any attack window!
By notifying the customer who tried to perform the action it helps drive user
behaviour and lets them know why the security group keeps reverting their 0.0.0.0/0
rule additions on them!

.. code-block:: yaml

   policies:
     - name: high-risk-security-groups-remediate
       resource: security-group
       description: |
         Remove any rule from a security group that allows 0.0.0.0/0 or ::/0 (IPv6) ingress
         and notify the user  who added the violating rule.
       mode:
           type: cloudtrail
           events:
             - source: ec2.amazonaws.com
               event: AuthorizeSecurityGroupIngress
               ids: "responseElements.securityGroupRuleSet.items[].groupId"
             - source: ec2.amazonaws.com
               event: AuthorizeSecurityGroupEgress
               ids: "responseElements.securityGroupRuleSet.items[].groupId"
             - source: ec2.amazonaws.com
               event: RevokeSecurityGroupEgress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: RevokeSecurityGroupIngress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: ModifySecurityGroupRules
               ids: "requestParameters.ModifySecurityGroupRulesRequest.GroupId"
       filters:
         - or:
               - type: ingress
                 Cidr:
                   value: "0.0.0.0/0"
               - type: ingress
                 CidrV6:
                   value: "::/0"
       actions:
           - type: remove-permissions
             ingress: matched
           - type: notify
             template: default.html
             priority_header: 1
             subject: "Open Security Group Rule Created-[custodian {{ account }} - {{ region }}]"
             violation_desc: "Security Group(s) Which Had Rules Open To The World:"
             action_desc: |
                 "Actions Taken:  The Violating Security Group Rule Has Been Removed As It Typically
                 Allows Direct Incoming Public Internet Traffic Access To Your Resource Which Violates Our
                 Company's Cloud Security Policy.  Please Refer To Our Company's Cloud Security Best
                 Practices Documentation.  If This Ingress Rule Is Required You May Contact The Security
                 Team To Request An Exception."
             to:
                 - CloudCustodian@Company.com
                 - event-owner
             transport:
                 type: sqs
                 queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
                 region: us-east-1

By including ``- event-owner`` in the notify's to: field it tells Cloud Custodian
to extract the id of the user who made the API call for the event and email them.
Being that the above policy runs in a cloudtrail mode the API call's metadata event
is present which is why the example uses event-owner.  If you were to remove the ``mode:``
statement on the example policy and run it in a poll mode instead you could change
``- event-owner`` to ``- resource-owner`` which would rely on the resources tags for
a id or email to send the notification to as no API event would be available at that time.
Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
