EC2 - auto-tag aws userName on resources
========================================

- Note that this can work for other resources besides EC2, and the principalId is optional. principalId tag is useful if you want to enforce users not being able to shut down each others VMs unless their principalId matches (meaning they originally spun up the resource). Documentation about principalId here: https://aws.amazon.com/blogs/security/how-to-automatically-tag-amazon-ec2-resources-in-response-to-api-events/

  .. code-block:: yaml

     policies:
     - name: ec2-auto-tag-user
       resource: ec2
       mode:
         type: cloudtrail
         role: arn:aws:iam::{account_id}:role/custodian-auto-tagger
         # note {account_id} is optional. If you put that there instead of
         # your actual account number, when the policy is provisioned it
         # will automatically inherit the account_id properly
         events:
           - RunInstances
       filters:
         - tag:CreatorName: absent
       actions:
         - type: auto-tag-user
           tag: CreatorName
           principal_id_tag: CreatorId