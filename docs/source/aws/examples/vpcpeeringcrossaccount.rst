.. _vpcpeeringcrossaccount:

VPC - Notify On Invalid External Peering Connections
=====================================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a new VPC Peering Connection is created.  The policy will then check
to see if the peering accepter account id and peering requester account id are both
AWS account numbers owned by you.  This is done by having the account ids from
the CloudWatch Event compared against a S3 hosted CSV of your AWS account numbers.
You must provide the CSV file of your account numbers or you can hardcode your account
numbers into the policy if you have a small static number of accounts.  The CSV would
look something like:
"271212121293","171717171716","27272727272724","121212112128","118118118118"

.. code-block:: yaml

   policies:

    - name: vpc-peering-cross-account-checker-real-time
      resource: peering-connection
      mode:
         type: cloudtrail
         events:
            - source: ec2.amazonaws.com
              event: CreateVpcPeeringConnection
              ids: 'responseElements.vpcPeeringConnection.vpcPeeringConnectionId'
         timeout: 90
         memory: 256
         role: arn:aws:iam::{account_id}:role/Cloud_Custodian_EC2_Lambda_Role
      description: |
        When a new peering connection is created the Accepter and Requester account
        numbers are compared and if they aren't both internally owned accounts then the
        cloud and security teams are notified to investigate and delete the peering connection.
      filters:
        - or:
            - type: event
              key: "detail.responseElements.vpcPeeringConnection.accepterVpcInfo.ownerId"
              op: not-in
              value_from:
                url: s3://s3bucketname/AccountNumbers.csv
                format: csv2dict
            - type: event
              key: "detail.responseElements.vpcPeeringConnection.requesterVpcInfo.ownerId"
              op: not-in
              value_from:
                url: s3://s3bucketname/AccountNumbers.csv
                format: csv2dict
      actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "ATTN!! External VPC Peering Violation [custodian {{ account }} - {{ region }}]"
           violation_desc: |
               VPC Peers are not to be setup to or from external AWS accounts
               so this policy verifies that both the source and destination
               accounts are internally owned. If the peering connection is going
               to/from an external account, this policy will email the Cloud and
               Security Teams as well as the customer.
           action_desc: |
               Please investigate this VPC Peering connection and terminate it
               if it's connecting to a unapproved external VPC
           to:
             - CloudTeam@company.com
             - security@company.com
             - resource-contact
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXXXXXX/cloud-custodian-mailer
             region: us-east-1




The following policy runs in pull mode and will scan all existing vpc peering connections
to see if any of them have external connections.  You will notice that the filters syntax
to pull the accepter and requester ids is slightly different between these 2 policies.
The first one pulls the information from the CloudTrail API event metadata and the second
policy uses information pulled back from a describe_vpc_peering_connections API call.
Using both policies allows you to check both new and existing peering connections.

.. code-block:: yaml

   policies:

    - name: vpc-peering-cross-account-checker-pull
      resource: peering-connection
      description: |
        Checks existing VPC Peering Connections to see if the Accepter
        and Requester account numbers are both internally owned accounts.
        If a connection is going to/from an external AWS account then the
        cloud and security teams are notified of the violating peering connection.
      filters:
        - or:
            - type: value
              key: "RequesterVpcInfo.OwnerId"
              op: not-in
              value_from:
                url: s3://s3bucketname/AccountNumbers.csv
                format: csv2dict
            - type: value
              key: "AccepterVpcInfo.OwnerId"
              op: not-in
              value_from:
                url: s3://s3bucketname/AccountNumbers.csv
                format: csv2dict
      actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "ATTN!! External VPC Peering Violation [custodian {{ account }} - {{ region }}]"
           violation_desc: |
               VPC Peers are not to be setup to or from external AWS accounts
               so this policy verifies that both the source and destination
               accounts are internally owned. If the peering connection is going
               to/from an external account, this policy will email the Cloud and
               Security Teams as well as the customer.
           action_desc: |
               Please investigate this VPC Peering connection and terminate it
               if it's connecting to a unapproved external VPC
           to:
             - CloudTeam@company.com
             - security@company.com
             - resource-contact
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXXXXXX/cloud-custodian-mailer
             region: us-east-1


Note that for email delivery to work with the ``notify`` action, the cloud custodian mailer tool must be installed, configured, and running.  See https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/c7n_mailer for docs.
