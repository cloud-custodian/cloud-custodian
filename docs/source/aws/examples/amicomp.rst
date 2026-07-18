AMI - Stop EC2 using Unapproved AMIs
====================================

.. code-block:: yaml

    policies:
      - name: ec2-invalid-ami
        resource: ec2
        comment: |
          Find all running EC2 instances that are using invalid AMIs and stop them
        filters:
          - "State.Name": running
          - type: value
            key: ImageId
            op: in
            value:
              - ami-12324567 # Invalid
              - ami-12324567 # Invalid
              - ami-12324567 # Invalid
              - ami-12324567 # Invalid
              - ami-12324567 # Invalid
        actions:
          - stop
