.. _accountaccountflowlog:

Account - Flow Log Configuration Check
=======================

The following example policy will find any flow log in your region that is not
properly configured and notify a group via email.

.. code-block:: yaml

   policies:
     - name: account-flow-log-check
       resource: account
       filters:
         - not:
              - type: flow-logs
                enabled: true
                set-op: or
                op: equal
                traffic-type: all
                log-group: myVPCFlowLogs
                status: active
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "Cloud Custodian - VPC Flow Log(s) Not Setup Properly"
           violation_desc: "The Following Flow Logs Are Invalid:"
           action_desc: "Actions Taken:  Notification Only"
           to:
              - CloudCustodian@Company.com
           transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
              region: us-east-1

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
