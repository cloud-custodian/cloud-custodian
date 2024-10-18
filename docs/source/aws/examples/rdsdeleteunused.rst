.. _rdsdeleteunused:

RDS - Delete Unused Databases With No Connections
=================================================

The following example policy workflow uses the mark-for-op and marked-for-op filters and
actions to chain together a set of policies to accomplish a task.  In this example it
will find any RDS that is older than 14 days that has had no connections to it in the last
14 days and tag it with a delete op and date 14 days out. The policy workflow will also
email the RDS resource owner to inform them of the upcoming stopping and deletion if the
RDS remains unused. If a customer connects to the RDS before the 14 day window it will
get unmarked so it doesn't get deleted.

Note the use of the notify action requires the Cloud Custodian mailer to be installed
and configured.

.. code-block:: yaml

     vars:
       metrics-filters: &metrics-filter
             type: metrics
             name: DatabaseConnections
             days: 14
             value: 0
             op: equal
     
     policies:

     - name: rds-unused-databases-notify-step1
       resource: rds
       description: |
         Take the average number of connections over 14 days for databases that are greater than 14
         days old and notify the resources owner on any unused RDS and mark for delete action in 14 days.
       filters:
         - "tag:c7n_rds_unused": absent
         - type: value
           value_type: age
           key: InstanceCreateTime
           value: 14
           op: greater-than
         - <<: *metrics-filter
         - or:
             - "tag:Resource Contact": present
             - "tag:CreatorName": present
       actions:
         - type: mark-for-op
           tag: c7n_rds_unused
           op: delete
           days: 14
         - type: notify
           template: default.html
           priority_header: 1
           subject: "RDS - Unused Database - [custodian {{ account }} - {{ region }}]"
           violation_desc: "RDS Instance has had no connections in the last 2 weeks and is unused:"
           action_desc: |
               "Actions Taken:  Database deletion has been scheduled for 14 days from now.
               At this point we are just notifying you of the upcoming deletion if not used."
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
               type: sqs
               queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
               region: us-east-1

     - name: rds-unused-databases-notify-step2
       resource: rds
       description: |
         Take the average number of connections over 21
         days and notify on any unused RDS that have already been marked for delete
       filters:
         - "tag:c7n_rds_unused": present
         - type: marked-for-op
           tag: c7n_rds_unused
           op: delete
           skew: 7
         - type: value
           value_type: age
           key: InstanceCreateTime
           value: 21
           op: gte
         - <<: *metrics-filter
         - or:
             - "tag:Resource Contact": present
             - "tag:CreatorName": present
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "RDS - URGENT - Unused Database - [custodian {{ account }} - {{ region }}]"
           violation_desc: |
               "RDS Instance has had no connections in the last 3 weeks and is unused and will be stopped
               hourly in 5 days (if supported by DB type) and then deleted 2 days after its stopped:"
           action_desc: |
               "Actions Taken:  Hourly database stopping and email will occur in 5 days and deleted will occur in 7 days.
               At this point we are just notifying you of the upcoming stoppage and deleted if not used"
           to:
             - resource-owner
           transport:
               type: sqs
               queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
               region: us-east-1

     - name: rds-unused-databases-stop-and-nag-hourly-step3
       resource: rds
       mode:
           type: periodic
           schedule: "rate(1 hour)"
           timeout: 300
       description: |
         This policy deploys a Lambda function triggered hourly by a CloudWatch Event.
         It averages connections over 26 days, stops the RDS, and notifies resource
         owners hourly about unused databases marked for deletion.
       filters:
         - "tag:c7n_rds_unused": present
         - type: marked-for-op
           tag: c7n_rds_unused
           op: delete
           skew: 1
         - type: value
           value_type: age
           key: InstanceCreateTime
           value: 26
           op: gte
         - <<: *metrics-filter
         - or:
             - "tag:Resource Contact": present
             - "tag:CreatorName": present
       actions:
         - type: notify
           template: default.html
           priority_header: 1
           subject: "RDS - URGENT!!! - Unused Database! - [custodian {{ account }} - {{ region }}]"
           violation_desc: |
               "RDS Instance has had no connections in the last 26 days and is unused
               and will be deleted in less than 48 hours"
           action_desc: |
               "Actions Taken: Hourly Stopping of RDS and notify.  Deletion will occur in less than
               48 hours. Please connect to the RDS or snapshot it if you don't need it at this time."
           to:
             - resource-owner
           transport:
               type: sqs
               queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
               region: us-east-1

     - name: rds-unused-databases-delete-step4
       resource: rds
       description: |
         Take the average number of connections over 28 days and delete
         any unused databases that have already been marked for delete
       filters:
         - "tag:c7n_rds_unused": present
         - type: marked-for-op
           tag: c7n_rds_unused
           op: delete
         - type: value
           value_type: age
           key: InstanceCreateTime
           value: 28
           op: gte
         - <<: *metrics-filter
         - or:
             - "tag:Resource Contact": present
             - "tag:CreatorName": present
       actions:
         - type: delete
           skip-snapshot: true
         - type: notify
           template: default.html
           priority_header: 1
           subject: "RDS - URGENT!!! - Unused Database Deleted! - [custodian {{ account }} - {{ region }}]"
           violation_desc: "RDS Instance has had no connections in the last 28 days and has been deleted."
           action_desc: "Actions Taken: RDS Instance(s) have been deleted."
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
               type: sqs
               queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
               region: us-east-1

     - name: rds-unused-databases-unmark
       resource: rds
       description: |
         The policy takes the average number of connections over 14 days and if there are connections
         then unmark the RDS instance and notify the resource owner.
       filters:
         - "tag:c7n_rds_unused": present
         - type: value
           value_type: age
           key: InstanceCreateTime
           value: 14
           op: gte
         - type: metrics
           name: DatabaseConnections
           days: 14
           value: 0
           op: gt
         - or:
             - "tag:Resource Contact": present
             - "tag:CreatorName": present
       actions:
         - type: remove-tag
           tags: ["c7n_rds_unused"]
         - type: notify
           template: default.html
           priority_header: 1
           subject: "RDS - Previously Unused DB Unmarked! - [custodian {{ account }} - {{ region }}]"
           violation_desc: |
               "RDS Instance that previously had no connections for over 2 weeks is now showing
               connections and it has been unmarked for deletion."
           action_desc: "Actions Taken: RDS Instance(s) have been unmarked. No further action needed"
           to:
             - CloudCustodian@Company.com
             - resource-owner
           transport:
               type: sqs
               queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
               region: us-east-1
