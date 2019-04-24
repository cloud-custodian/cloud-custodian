.. _ec2offhours:

EC2 - Offhours Support
======================

Offhours are based on current time of the machine that is running custodian.
Note, in this case you could tag an instance with the following two tags:
``StopAfterHours: off=(M-F,18);tz=est;`` and ``StartAfterHours: on=(M-F,8)``.
This would have the instance turn off every weekday at 6pm NY time, and turn on
every day at 8am California time (since if no tz is set, it uses the default
which is pt). Note when custodian runs, if it's 6:00pm or 6:59 pm NY time, it
will shut down the VM you tagged this way. The key is the hour integer on the NY
clock matching 18. If custodian runs at 5:59pm or 7:00pm NY time, it won't shut
down the VM. Same idea for starting.

The reason we filter for only seeing instances older than 1 hour, if a dev is
on a VM that is shut down by the off hours schedule, and they turn it back on,
if we run custodian again we don't want to keep shutting down the VM on the dev
repeatedly.

.. code-block:: yaml

   policies:
     - name: stop-after-hours
       resource: ec2
       filters:
         - type: offhour
           tag: CustodianOffHours
           default_tz: pt
           offhour: 19
         - type: instance-age
           hours: 1
       actions:
         - stop

     - name: start-after-hours
       resource: ec2
       filters:
         - type: onhour
           tag: CustodianOffHours
           default_tz: pt
           onhour: 7
         - type: value
           value: 1
           key: LaunchTime
           op: less-than
           value_type: age
       actions:
         - start

For detailed information on offhours/onhours support and configuration, see
:ref:`offhours`.
