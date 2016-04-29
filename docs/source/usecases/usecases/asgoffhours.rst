ASG - Offhours Support
======================

- Offhours are based on current time of the instance

.. code-block:: yaml

   policies:
     - name: offhour-stop-19
       resource: asg
       comments: |
         Daily stoppage at 7pm
       filters:
         - type: offhour
           tag: custodian_downtime
           offhour: 22
       actions:
         - stop
   
     - name: onhour-start-10
       resource: asg
       comments: |
         Daily start at 10am
       filters:
         - type: onhour
           tag: custodian_downtime
           onhour: 10
       actions:
         - start
         
