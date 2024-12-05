EIP - Garbage Collect Unattached Elastic IPs
============================================

Use the ``mark-for-op`` action to mark a resource for action later. One common
pattern to follow is to mark a resource with an operation (example: release) in
n days. In the subsequent days leading up to the marked date, run a unmark or
untag policy if the resource has become compliant in the mean time.

You can use this principle to implement garbage collection on resources. In this
example, Custodian will first mark all unattached Elastic IPs for removal. The
next policy will then unmark any EIP that has been attached and has the
``maid_status`` tag, indicating that it had been previously marked. Finally, the
third policy will filter in any resources that have been marked and run the
``release`` action.

It is important to note that the release policy will need to be run on the day that
the resource is marked for, else the resource will still exist in the account.
The mark operation only tags the resource with metadata about the upcoming operation.
Operationally, the policy still must be executed on the day that is specified in
the tag.

Note: all resources that are ``marked-for-op`` up to and including the current
date will be filtered in when utilizing the ``marked-for-op`` filter.

  .. code-block:: yaml

    vars:
      notify: &notify
        type: notify
        to:
          - slack://#slack-channel
        subject: "EIP - No Instances Attached - [custodian {{ account }} - {{ region }}]"
        transport:
          type: sqs
          queue: https://sqs.us-east-2.amazonaws.com/123456789012/mailer
          region: us-east-2
      run_mode: &run_mode
        type: periodic
        schedule: "rate(1 day)"
        tags:
          app: "c7n"
          env: "tools"
          account: "{account_id}"
      eip_filters: &eip_filters
        - InstanceId: absent
        - AssociationId: absent

    policies:
      - name: unused-eip-mark
        resource: elastic-ip
        description: "Mark any EIP with no instances attached for action in 7 days"
        filters:
          - "tag:maid_status_eip": absent
          - and: *eip_filters
        mode:
          <<: *run_mode
        actions:
          - type: mark-for-op
            tag: maid_status_eip
            days: 7
            op: release

      - name: unused-eip-unmark-if-in-use
        resource: elastic-ip
        description: |
          Remove the maid_status_eip tag from any eip which has instances attached
        filters:
          - "tag:maid_status_eip": not-null
          - not:
            - or: *eip_filters
        mode:
          <<: *run_mode
        actions:
          - type: remove-tag
            tags: [maid_status_eip]

      - name: unused-eip-action
        resource: elastic-ip
        description: "Release EIP after 7 days of having no instances"
        filters:
          - "tag:maid_status_eip": not-null
          - type: marked-for-op
            op: release
            tag: maid_status_eip
        mode:
          <<: *run_mode
        actions:
          - type: release
          - <<: *notify
            action_desc: "EIP released"
            violation_desc: "EIP has been unused for 7 days"
