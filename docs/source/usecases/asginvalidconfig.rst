.. _asginvalidconfig:

AutoScaling Group - Verify ASGs have valid configurations
=========================================================

The following example policy will check all AutoScaling Groups for configuration
issues which could prevent the ASG from functioning properly.  The following items
are checked: invalid subnets, invalid security groups, invalid key pair name,
invalid launch config volume snapshots, invalid amis, invalid elb health check etc.

.. code-block:: yaml

   policies:
     - name: asg-invalid-configuration
       resource: asg
       filters:
         - invalid
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "ASG-Invalid Config-[custodian {{ account }} - {{ region }}]"
           violation_desc: |
               "New ASG instances may fail to launch or scale! The following Autoscaling
               Groups have invalid AMIs, SGs, KeyPairs, Launch Configs, or Health Checks"
           action_desc: |
               "Actions Taken:  Notification Only. Please investigate and fix your ASGs
               configuration to prevent you from having any outages or issues"
           to:
              - CloudAdmins@Company.com
              - resource-owner
           transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
              region: us-east-1

Note that the ``notify`` action requires the cloud custodian mailer tool to be installed.
