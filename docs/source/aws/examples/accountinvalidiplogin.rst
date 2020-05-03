.. _accountinvalidiplogin:

Account - Login From Invalid IP Address
=======================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a user logs in from an invalid IP address. If the source IP address of
the event is outside of the provided ranges in the policy then notify the admins
security team for further investigation. Using the cloudtrail mode provides near
real-time auto-remediation (typically within 1-2 mins) of the event occurring.
Having such a quick auto-remediation action greatly reduces an attack window!
By notifying the cloud admins or security team they can validate the login and
revoke the login session if it's not valid followed by changing the password for
or disabling the compromised user etc.

In the below example the filter being applied is regex and reads as follows:
-Notify if the source IP address of the event is not from one of the valid IP CIDRs
- 158.103.0.0/16
- 142.179.0.0/16
- 187.39.0.0/16
- 12.0.0.0/8
You can generate the Regex for IP ranges on a site like:
http://www.analyticsmarket.com/freetools/ipregex

.. code-block:: yaml

   policies:

     - name: invalid-ip-address-login-detected
       resource: account
       description: |
         Notifies on invalid external IP console logins
       mode:
          type: cloudtrail
          events:
             - ConsoleLogin
       filters:
         - not:
             - type: event
               key: 'detail.sourceIPAddress'
               value: |
                  '^((158\.103\.|142\.179\.|187\.39\.)([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])
                  \.([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5]))|(12\.([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])
                  \.([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])\.([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5]))$'
               op: regex
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "Login From Invalid IP Detected - [custodian {{ account }} - {{ region }}]"
           violation_desc: "A User Has Logged In Externally From A Invalid IP Address Outside The Company's Range:"
           action_desc: |
               "Please investigate and revoke the invalid session along
               with any other restrictive actions if appropriate"
           to:
             - CloudAdmins@Company.com
             - SecurityTeam@Company.com
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
             region: us-east-1

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
