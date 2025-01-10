EC2 - Old Instance Report
=========================

.. code-block:: yaml

    policies:
      - name: ec2-old-instances
        resource: ec2
        comment: |
          Report running instances older than 60 days
        filters:
          - "State.Name": running
          - type: instance-age
            days: 60

      # Use Case: Report all AMIs that are 120+ days or older

      - name: ancient-images-report
        resource: ami
        comment: |
          Report on all images older than 90 days which should be de-registered.
        filters:
          - type: image-age
            days: 120


Instance Age Filter
  The instance age filter allows for filtering the set of EC2 instances by
  their LaunchTime, i.e. all instances older than 60 or 90 days. The default
  date value is 60 days if otherwise unspecified.
  Configuring a specific value for instance-age to report all instances older
  than 90 days.

  .. code-block:: yaml

     policies:
       - name: old-instances
         resource: ec2
         filters:
           - type: instance-age
             days: 90
