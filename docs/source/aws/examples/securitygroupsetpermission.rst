.. _securitygroupsaddpermission:

Security Groups - add permission
=================================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a user creates or modifies a security group. This provides near real-time
auto-remediation action (typically within a minute) of the security group change.
Having such a quick auto-remediation action greatly reduces any attack window!
User defined rule is added to the filtered results.

.. code-block:: yaml

   policies:
     - name: sg-add-permission
       resource: security-group
       description: |
         Add rule to a security group. Filter any security group that allows 0.0.0.0/0 or ::/0 (IPv6) ingress
         on port 22, remove the rule and add user defined sg rule
       mode:
           type: cloudtrail
           events:
             - source: ec2.amazonaws.com
               event: AuthorizeSecurityGroupIngress
               ids: "requestParameters.groupId"
             - source: ec2.amazonaws.com
               event: RevokeSecurityGroupIngress
               ids: "requestParameters.groupId"
       filters:
          - or:
                - type: ingress
                  IpProtocol: "-1"
                  Ports: [22]
                  Cidr: "0.0.0.0/0"
                - type: ingress
                  IpProtocol: "-1"
                  Ports: [22]
                  CidrV6: "::/0"
       actions:
        - type: remove-permissions
          ingress: matched
        - type: add-permissions
          PermissionType: "ingress"
          IpProtocol: "TCP"
          FromPort: 22
          ToPort: 22
          Cidr: ["2.2.2.2/32","1.1.1.1/32"]