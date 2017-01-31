EC2 - Offhours Support
======================

- Offhours are based on current time of the instance

.. code-block:: yaml

   policies:
     - name: offhour-stop-19
       resource: ec2
       comments: |
         Daily stoppage at 7pm
       filters:
         - type: offhour
           tag: c7n_downtime
           hour: 22
       actions:
         - stop
   
     - name: onhour-start-10
       resource: ec2
       comments: |
         Daily start at 10am
       filters:
         - type: onhour
           tag: c7n_downtime
           hour: 10
       actions:
         - start
         