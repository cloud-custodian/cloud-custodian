Tag Compliance Across Resources (EC2, ASG, ELB, S3, etc)
========================================================

Mark
  Tag instances with mark instances matching filters with a 'c7n_status' tag by
  default and configurable value.

  Here's an example of renaming an extant tag

  .. code-block:: yaml

     policies:

       - name: ec2-tag-instances
         resource: ec2
         filters:
           - "tag:CostCenter": foobar
         actions:
           - type: mark
             tag: CostCenter
             msg: barrum


Report on Tag Compliance
  .. code-block:: yaml

     policies:

       - name: ec2-tag-compliance
         resource: ec2
         comment: |
           Report on total count of non compliant instances
         filters:
           - "tag:Owner": absent
           - "tag:CostCenter": absent
           - "tag:Project": absent


Enforce Tag Compliance
  All instances that do not have the three required tags (CostCenter, Owner, Project) will
  be stopped hourly after 2 days, and terminated after 5 days.

  .. code-block:: yaml

     policies:

     - name: ec2-tag-compliance-mark
       resource: ec2
       comment: |
         Find all (non-ASG) instances that are not conformant
         to tagging policies, and tag them for stoppage in 1 days.
       filters:
         - "tag:aws:autoscaling:groupName": absent
         - "tag:c7n_status": absent
         - "tag:Owner": absent
         - "tag:CostCenter": absent
         - "tag:Project": absent
       actions:
         - type: mark-for-op
           op: stop
           days: 1

     - name: ec2-tag-compliance-unmark
       resource: ec2
       comment: |
         Any instances which have previously been marked as
         non compliant with tag policies, that are now compliant
         should be unmarked as non-compliant.
       filters:
         - "tag:Owner": not-null
         - "tag:CostCenter": not-null
         - "tag:Project": not-null
         - "tag:c7n_status": not-null
       actions:
         - unmark
         - start

     - name: ec2-tag-compliance-stop
       resource: ec2
       comment: |
         Stop all non autoscaling group instances previously marked
         for stoppage by today's date, and schedule termination in
         2 days. Also verify that they continue to not meet tagging
         policies.
       filters:
         - "tag:aws:autoscaling:groupName": absent
         - "tag:Owner": absent
         - "tag:CostCenter": absent
         - "tag:Project": absent
         - type: marked-for-op
           op: stop
       actions:
         - stop
         - type: mark-for-op
           op: terminate
           days: 3

     - name: ec2-tag-compliance-terminate
       resource: ec2
       comment: |
         Terminate all stopped instances marked for termination
         by today's date.
       filters:
         - "tag:aws:autoscaling:groupName": absent
         - "tag:Owner": absent
         - "tag:CostCenter": absent
         - "tag:Project": absent
         - type: marked-for-op
           op: terminate
       actions:
         - type: terminate
           force: true

     - name: ec2-tag-compliance-nag-stop
       resource: ec2
       comment: |
         Stop all instances marked for termination every hour
         starting 1 day before their termination.
       filters:
         - "tag:aws:autoscaling:groupName": absent
         - "tag:CostCenter": absent
         - "tag:Owner": absent
         - "tag:Project": absent
         - type: marked-for-op
           op: terminate
           skew: 1
       actions:
         - stop
