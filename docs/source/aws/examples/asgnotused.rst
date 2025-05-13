AMI - ASG Garbage Collector
====================================
ASG garbage collector which mean that:

Check if an ASG has minSize = 0 and DesiredCapacity = 0
Mark the ASG as ops to alert.
If value won't change cloudCustodian will send an alert with ASGs.

.. code-block:: yaml

   policies:
    - name: asg-mark-as-unused
      resource: asg
      comments: |
        Mark any unused ASG checking it every day.
      filters:
        - type: value
          key: MinSize
          value: 0
          op: eq
        - type: value
          key: DesiredCapacity
          value: 0
          op: eq
      actions:
        - type: mark-for-op
          op: notify
          days: 30
    - name: asg-unmark-as-unused
      resource: asg
      comments: |
        Unmark any ASG that has a value greater than 0.
      filters:
        - type: value
          key: DesiredCapacity
          op: greater-than
          value: 0
        - "tag:maid_status": not-null
      actions:
        - unmark
    - name: asg-slack-alert
      resource: asg
      comments: |
        Alert for ASG which have MinSize < 0 and DesiredCapacity < 0
      filters:
        - "tag:maid_status": not-null
        - type: marked-for-op
          op: notify
      actions:
        - type: notify
          slack_template: slack
          violation_desc: Having ASG with both (DesiredCapacity and MinSize) = 0.
          action_desc: Please investigate if you can delete this ASG.
          to:
            - https://hooks.slack.com/services/TXXXXX/XXXXXX/XXXxxXXX
          transport:
            type: sqs
            queue: https://sqs.us-east-1.amazonaws.com/12345678900/cloud-custodian-mailer
            region: us-east-1
