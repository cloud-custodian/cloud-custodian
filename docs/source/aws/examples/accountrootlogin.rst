.. _accountrootlogin:

Account - Detect Root Logins
============================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime the root user of the account logs in. Typically the root user of an AWS
account should never need to login after the initial account setup and root user
access should be very tightly controlled with hardware MFA and other controls
as root has full control of everything in the account. Having this visibility
to see if and when someone logs in as root is very important.

.. code-block:: yaml

   policies:

     - name: root-user-login-detected
       resource: account
       description: |
         Notifies Security and Cloud Admins teams on any AWS root user console logins
       mode:
          type: cloudtrail
          events:
             - ConsoleLogin
       filters:
          - type: event
            key: "detail.userIdentity.type"
            value_type: swap
            op: in
            value: Root
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "Root User Login Detected! - [custodian {{ account }} - {{ region }}]"
           violation_desc: "A User Has Logged Into the AWS Console With The Root User:"
           action_desc: |
               Please investigate and if needed revoke the root users session along
               with any other restrictive actions if it's an unapproved root login
           to:
             - CloudAdmins@Company.com
             - SecurityTeam@Company.com
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
             region: us-east-1

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
