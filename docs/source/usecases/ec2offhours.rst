EC2 - Offhours Support
======================

- Offhours are based on current time of the instance

.. code-block:: yaml

   policies:
     - name: offhour_stop_19
       resource: ec2
       comments: |
         Daily stoppage at 7pm
       filters:
         - type: offhour
           tag: c7n_downtime
           offhour: 22
           default_tz: est
       actions:
         - stop
   
     - name: onhour_start_10
       resource: ec2
       comments: |
         Daily start at 10am
       filters:
         - type: onhour
           tag: c7n_downtime
           onhour: 10
           default_tz: est
       actions:
         - start
         
