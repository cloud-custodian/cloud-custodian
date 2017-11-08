.. _securitygroupsdetectremediate:

Security Groups - Detect and Remediate Violations
=================================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a user creates or modifies a security group. This provides auto-remediation
and near real-time action (typically within a minute) of the security group change.
By notifying the customer who tried to perform the action it helps drive user
behaviour and lets them know why the security group keeps reverting their 0.0.0.0/0
rule additions on them!

.. code-block:: yaml

   policies:
     - name: high-risk-security-groups-remediate
       resource: security-group
       description: |
         Remove any rule from a security group that allows 0.0.0.0/0 ingress
         and notify the user  who added the violating rule.
       mode:
           type: cloudtrail
           events:
             - source: ec2.amazonaws.com
               event: AuthorizeSecurityGroupIngress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: AuthorizeSecurityGroupEgress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: RevokeSecurityGroupEgress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: RevokeSecurityGroupIngress
               ids: "requestParameters.groupId"
       filters:
         - type: ingress
           Cidr:
               value: "0.0.0.0/0"
       actions:
           - type: remove-permissions
             ingress: matched
           - type: notify
             template: default.html
             priority_header: 1
             subject: "Open Security Group Rule Created-[custodian {{ account }} - {{ region }}]"
             violation_desc: "Security Group(s) Which Had Rules Open To The World:"
             action_desc: |
                 "Actions Taken:  The Violating Security Group Rule Has Been Removed As It
                 Violates Our Company's Cloud Policy.  Please Refer To The Cloud FAQ."
             to:
                 - CloudCustodian@Company.com
                 - event-owner
             transport:
                 type: sqs
                 queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
                 region: us-east-1

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
