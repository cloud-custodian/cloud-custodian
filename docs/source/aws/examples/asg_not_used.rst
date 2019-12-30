AMI - ASG Garbage Collector
====================================

.. code-block:: yaml


  - name: asg-mark-as-unused
    resource: asg
    mode:
      type: periodic
      schedule: "rate(24 hours)"
      role: c7n_cloud_custodian_role
      tags:
        env: env
        role: role
        service: service
        owner: owner
        team: team
    comments: |
      Mark any unused ASG checking it every day.
    filters:
      - and:
        - type: value
          key: MinSize
          value: 1
          op: less-than
        - type: value
          key: DesiredCapacity
          value: 1
          op: less-than
    actions:
        - type: mark-for-op
          op: delete
          days: 30
  - name: asg-unmark-as-unused
    resource: asg
    mode:
      type: periodic
      schedule: "rate(12 hours)"
      role: c7n_cloud_custodian_role
      tags:
        env: env
        role: role
        service: service
        owner: owner
        team: team
    comments: |
      Unmark any ASG which has a value upper than 0.
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
    mode:
      type: periodic
      schedule: "rate(10 minutes)"
      role: c7n_cloud_custodian_role
      tags:
        env: env
        role: role
        service: service
        owner: owner
        team: team
    comments: |
      Alert for ASG which have MinSize < 0 and DesiredCapacity < 0
    filters:
      - "tag:maid_status": not-null
      - type: marked-for-op
        op: delete
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
