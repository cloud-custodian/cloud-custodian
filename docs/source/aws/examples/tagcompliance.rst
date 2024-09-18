Tag Compliance Across Resources (EC2, ASG, ELB, S3, etc)
========================================================

Add or Change Tag Values
~~~~~~~~~~~~~~~~~~~~~~~~

  The ``tag`` action can apply a tag to a resource. If that
  tag already exists, the value will be updated.

  .. note::

    Cloud Custodian tagging operations operate on tag keys specified
    in the policy. If a policy *doesn't* specify a tag key,
    Custodian will use the ``maid_status`` tag by default.

    Prefer explicitly specifying tag keys to avoid confusion.

  Here's an example of changing the value of an extant ``CostCenter`` tag.

  .. code-block:: yaml

     policies:

       - name: ec2-tag-instances
         resource: ec2
         filters:
           - "tag:CostCenter": foobar
         actions:
           - type: tag
             key: CostCenter
             value: barrum


Report on Tag Compliance
~~~~~~~~~~~~~~~~~~~~~~~~

  This policy matches any EC2 instances that don't have ``Owner``, ``CostCenter``, or ``Project``
  tags defined.

  .. code-block:: yaml

     policies:

       - name: ec2-tag-compliance
         resource: ec2
         comment: |
           Report on total count of non compliant instances
         filters:
           - or:
               - "tag:Owner": absent
               - "tag:CostCenter": absent
               - "tag:Project": absent


Enforce Tag Compliance - EC2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  All EC2 non-AutoScaling instances that do not have the three required tags (``CostCenter``, ``Owner``, ``Project``)
  will be stopped hourly after 2 days, and terminated after 5 days.

  This set of policies uses the ``c7n_status`` tag to plan and execute delayed actions.

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
        - or:
            - "tag:Owner": absent
            - "tag:CostCenter": absent
            - "tag:Project": absent
      actions:
        - type: mark-for-op
          tag: c7n_status
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
        - type: remove-tag
          tags:
            - c7n_status

    - name: ec2-tag-compliance-stop
      resource: ec2
      comment: |
        Stop all non autoscaling group instances previously marked
        for stoppage by today's date, and schedule termination in
        2 days. Also verify that they continue to not meet tagging
        policies.
      filters:
        - "tag:aws:autoscaling:groupName": absent
        - type: marked-for-op
          tag: c7n_status
          op: stop
        - or:
            - "tag:Owner": absent
            - "tag:CostCenter": absent
            - "tag:Project": absent
      actions:
        - stop
        - type: mark-for-op
          tag: c7n_status
          op: terminate
          days: 3

    - name: ec2-tag-compliance-terminate
      resource: ec2
      comment: |
        Terminate all stopped instances marked for termination
        by today's date.
      filters:
        - "tag:aws:autoscaling:groupName": absent
        - type: marked-for-op
          tag: c7n_status
          op: terminate
        - or:
            - "tag:Owner": absent
            - "tag:CostCenter": absent
            - "tag:Project": absent
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
        - type: marked-for-op
          tag: c7n_status
          op: terminate
          skew: 1
        - or:
            - "tag:CostCenter": absent
            - "tag:Owner": absent
            - "tag:Project": absent
      actions:
        - stop

Enforce Tag Compliance - AutoScaling Groups
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  All AutoScaling Groups that do not have the 5 required tags:
  (Resource Contact, Billing Cost Center, Environment, Resource Purpose, Business Unit)
  will be suspended and stopped once after 24 hours and then hourly after 2 days,
  and terminated after 3 days.  We are using a custom tag named ``c7n_tag_compliance``
  to plan delayed actions, and `YAML anchors <https://support.atlassian.com/bitbucket-cloud/docs/yaml-anchors/>`_
  to reuse the same set of filters across multiple policies in the same file.

  .. code-block:: yaml

      vars:
        tag-filters: &tag-compliance-filters
              - "tag:Resource Contact": absent
              - "tag:Billing Cost Center": absent
              - "tag:Environment": absent
              - "tag:Resource Purpose": absent
              - "tag:Business Unit": absent

      policies:

      - name: asg-tag-compliance-mark-new-day-0
        resource: asg
        mode:
           type: cloudtrail
           events:
              - source: autoscaling.amazonaws.com
                event: CreateAutoScalingGroup
                ids: requestParameters.autoScalingGroupName
        description: |
          Marks newly launched non-compliant ASGs if missing any of the required tags
          also tags the owners.
        comments: |
          Your ASG and ASG instances do not have all the required tags on them and will be suspended
          in 24 hours if all the required tags have not been added.  If tags are not made compliant
          after 3 days your ASG and instances will be deleted.
        filters:
          - "tag:c7n_tag_compliance": absent
          - or: *tag-compliance-filters
        actions:
          - type: mark-for-op
            tag: c7n_tag_compliance
            op: suspend
            days: 1
          - type: auto-tag-user
            tag: CreatorName
            principal_id_tag: CreatorId
          - type: notify
            template: default.html
            priority_header: 1
            subject: "ASG - Missing Required Tags - [custodian {{ account }} - {{ region }}]"
            violation_desc:  |
              Your ASG and related servers are missing the required tags and is now marked
               for suspension if tags not added within 24 hours:
            action_desc: |
              "Actions Taken:  The ASG is marked to be suspended tomorrow if
              required tags don't get added to the ASG"
            to:
              - CloudCustodian@Company.com
              - event-owner
            transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXX/cloud-custodian-mailer
              region: us-east-1

      - name: asg-tag-compliance-unmark
        resource: asg
        mode:
            type: periodic
            schedule: "rate(5 minutes)"
        description: |
          Any ASG which have previously been marked as
          non compliant with tag policies, that are now compliant
          should be unmarked as non-compliant.
        comments: |
          Thank you for adding the required tags to your ASG!  It is now compliant
          and has been resumed if it was in a suspended state.
        filters:
          - "tag:c7n_tag_compliance": not-null
          - not:
            - or: *tag-compliance-filters
        actions:
          - type: unmark
            key: "c7n_tag_compliance"
          - resume
          - type: propagate-tags
            tags:
                - "Resource Contact"
                - "Billing Cost Center"
                - "Environment"
                - "Resource Purpose"
                - "Business Unit"
          - type: notify
            template: default.html
            priority_header: 1
            subject: "ASG - AutoScaling Group is now compliant - [custodian {{ account }} - {{ region }}]"
            violation_desc: |
              "Your ASG which was previously missing required tags is now compliant and won't be suspended:"
            action_desc: |
              "Actions Taken:  The ASG has been unmarked for suspending as its now compliant with tags"
            to:
              - resource-owner
            transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXX/cloud-custodian-mailer
              region: us-east-1

      - name: asg-tag-compliance-suspend-day-1
        resource: asg
        mode:
            type: periodic
            schedule: "rate(1 hour)"
        description: |
          Suspends the ASG and resizes to 0 instances as the tags are still not compliant
        comments: |
          Your ASG has been suspended and resized to 0 instances as they do not have all
          the required tags on them.  Please login to AWS and add the required tags to your ASG.
          Starting tomorrow hourly emails and suspensions will start occuring if the ASG is
          still not compliant. The following day your ASG will be deleted.
        filters:
          - or: *tag-compliance-filters
          - type: marked-for-op
            tag: c7n_tag_compliance
            op: suspend
          - type: value
            key: CreatedTime
            op: gte
            value_type: age
            value: 1
        actions:
          - suspend
          - type: mark-for-op
            tag: c7n_tag_compliance
            op: delete
            days: 2
          - type: notify
            template: default.html
            priority_header: 1
            subject: "ASG - !!!! Missing Required Tags !!!! - [custodian {{ account }} - {{ region }}]"
            violation_desc: |
              "Your ASG is missing the required tags and will be deleted in 2 days if still not compliant.
              Until then the ASG will be suspended every hour until tagged:"
            action_desc: |
              "Actions Taken:  The ASG has been suspended as it doesn't meet tagging requirements.
              Please tag your ASG.  ASG will be deleted in 2 days if not tagged."
            to:
              - resource-owner
            transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXX/cloud-custodian-mailer
              region: us-east-1

      - name: asg-tag-compliance-nag-stop-day-2
        resource: asg
        mode:
            type: periodic
            schedule: "rate(1 hour)"
        description: |
          Suspends ASGT and stops ASG instances every hour
          starting 1 day before their deletion if tags are still not compliant.
        filters:
          - or: *tag-compliance-filters
          - type: marked-for-op
            tag: c7n_tag_compliance
            op: delete
            skew: 1
          - type: value
            key: CreatedTime
            op: gte
            value_type: age
            value: 2
        actions:
          - suspend
          - type: notify
            template: default.html
            priority_header: 1
            subject: "ASG - AutoScaling Group Suspended!!! - [custodian {{ account }} - {{ region }}]"
            violation_desc: |
              "Your ASG is missing the required tags and will be deleted in less than 1 day if still
              not compliant.  Until then the ASG will be suspended every hour
              until tagged or Deleted:"
            action_desc: |
              "Actions Taken:  The ASG has been suspended and set to 0 instances as it doesn't meet
              tagging requirements.  Please tag your ASG now.
              ASG will be deleted in less than 1 day if not tagged."
            to:
              - resource-owner
            transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXX/cloud-custodian-mailer
              region: us-east-1

      - name: asg-tag-compliance-delete-day3
        resource: asg
        mode:
            type: periodic
            schedule: "rate(1 hour)"
        description: |
          Delete all ASG marked for deletion by today's date.
        comments: |
          Your ASG has been deleted as it still did not meet the required tag compliance!
        filters:
          - or: *tag-compliance-filters
          - type: marked-for-op
            tag: c7n_tag_compliance
            op: delete
          - type: value
            key: CreatedTime
            op: gte
            value_type: age
            value: 3
        actions:
          - type: delete
            force: true
          - type: notify
            template: default.html
            priority_header: 1
            subject: "ASG - ASG Deleted Due To Missing Tags - [custodian {{ account }} - {{ region }}]"
            violation_desc: "Your ASG is still missing the required tags :"
            action_desc: |
              "Actions Taken:  The ASG has been Deleted.
              A new ASG will need to be launched to replace this if needed.
              Please make sure to tag the new ASG"
            to:
              - CloudCustodian@Company.com
              - resource-owner
            transport:
              type: sqs
              queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXX/cloud-custodian-mailer
              region: us-east-1
