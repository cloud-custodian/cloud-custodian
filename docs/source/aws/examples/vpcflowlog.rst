.. _accountaccountflowlog:

VPC - Flow Log Configuration Check
======================================

The following example policy will find any VPC Flow Log in your region that is
not properly configured and notify a group via email.  Ensuring VPC Flow Logs
are enabled and setup properly is very important for compliance and security.
Flow Logs themselves capture IP traffic information to and from network
interfaces and can be used for troubleshooting traffic issues and monitoring
network traffic as a security tool.  See more info on example dashboarding
of VPC Flow Logs using Elasticsearch and Kibana
https://aws.amazon.com/blogs/aws/cloudwatch-logs-subscription-consumer-elasticsearch-kibana-dashboards/

.. code-block:: yaml

   policies:
     - name: vpc-flow-log-check
       resource: vpc
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
