.. _ec2unpatchedworkflow:

EC2 - Terminate Unpatchable Instances
=====================================

The following example policy workflow uses the mark-for-op and marked-for-op filters and
actions to chain together a set of policies to accomplish a task.  In this example it will
find and tag any instances that are in a stopped state.  The example specifies a custom tag
called c7n_stopped_instance and the value of the tag will be an op action of terminate for
60 days in the future.  The reasoning behind terminating unpatchable instances is after 60
days the instance will be far enough behind on patching and virus defs(if used) that
starting the instance after 60 days would  present too large of a security risk. 

Note the use of the skew option with the marked-for-op filter in some of the policies to
notify the resource owners X number of days ahead of the scheduled marked-for-op action date.

.. code-block:: yaml

   policies:

     - name: ec2-mark-stopped-instance
       resource: ec2
       description: |
         Mark any stopped ec2 instance for deletion in 60 days
         If an instance has not been started for 60 days or over
         then they will be deleted similar to internal policies as it wont be patched.
       filters:
         - "tag:c7n_stopped_instance": absent
         - "State.Name": stopped
       actions:
         - type: mark-for-op
           tag: c7n_stopped_instance
           op: terminate
           days: 60

     - name: ec2-unmark-previously-stopped
       resource: ec2
       description: |
         Unmark/untag any ec2 instance that was scheduled for deletion due to being stopped
         if they are currently running.
       filters:
         - "State.Name": running
         - "tag:c7n_stopped_instance": present
       actions:
         - type: unmark
           tags: ["c7n_stopped_instance"]

     - name: ec2-notify-before-delete-marked-14-days
       resource: ec2
       description: |
         Notify on any ec2 instances that will be deleted in 14 days if not started
       comments: |
         Your EC2 server will be terminated in 14 days if not started and patched by then.
         Please start your stopped servers and leave them on for 24 hours minimum to
         allow for patching to occur.
       filters:
         - type: marked-for-op
           tag: c7n_stopped_instance
           op: terminate
           skew: 14
       actions:
         - type: notify
           template: default.html
           priority_header: 2
           subject: "EC2 Stopped Instance Termination Scheduled! [custodian {{ account }} - {{ region }}]"
           violation_desc: "EC2(s) have been in a stopped state for 45 days and at 60 days will be termianted:"
           action_desc: |
               Your EC2 server will be terminated in 14 days if not started and patched by then.
               Please start your stopped servers and leave them on for 24 hours minimum to
               allow for patching to occur.
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
             region: us-east-1

     - name: ec2-notify-before-delete-marked-7-days
       resource: ec2
       description: |
         Notify on any ec2 instances that will be deleted in 7 days if not started
       filters:
         - type: marked-for-op
           tag: c7n_stopped_instance
           op: terminate
           skew: 7
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "EC2 Stopped Instance Termination Scheduled! [custodian {{ account }} - {{ region }}]"
           violation_desc: "EC2(s) have been in a stopped state for 53 days and at 60 days will be termianted:"
           action_desc: |
               Your EC2 server will be terminated in 7 days if not started and patched by then.
               Please start your stopped servers and leave them on for 24 hours minimum to
               allow for patching to occur.
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
             region: us-east-1

     - name: ec2-delete-marked
       resource: ec2
       description: |
         Terminate and notify on any ec2 instances that were scheduled
         for deletion if its been stopped for 60 days
         and no longer up-to-date on patching.
       filters:
         - type: marked-for-op
           tag: c7n_stopped_instance
           op: terminate
       actions:
         - type: terminate
           force: true
         - type: notify
           template: default.html
           priority_header: 1
           subject: "EC2 Stopped Instance Terminated [custodian {{ account }} - {{ region }}]"
           violation_desc: "EC2(s) had been stopped for 60 days and have now been terminated:"
           action_desc: |
               Your EC2 server has been terminated as its patching is too far out-of-date and
               beyond the 60 day window.
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
             type: sqs
             queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
             region: us-east-1
