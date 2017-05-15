EC2 - Offhours Support
======================

Offhours are based on current time of the machine that is running custodian. Note, in this case you could tag an instance with the following two tags: StopAfterHours: off=(M-F,18);tz=est; and StartAfterHours: on=(M-F,8). This would have the instance turn off every weekday at 6pm NY time, and turn on every day at 8am California time (since if no tz is set, it uses the default which is pt). Note when custodian runs, if it's 6:00pm or 6:59 pm NY time, it will shut down the VM you tagged this way. The key is the hour integer on the NY clock matching 18. If custodian runs at 5:59pm or 7:00pm NY time, it won't shut down the VM. Same idea for starting.

Policy values:

- weekends: default true, whether to leave resources off for the weekend
- weekend-only: default false, whether to turn the resource off only on the weekend
- tag: the tag name to use when configuring
- default_tz: the default timezone to use when interpreting offhours (REQUIRED)
- offhour: the time to turn instances off, specified in 0-23
- onhour: the time to turn instances on, specified in 0-23
- opt-out: default behavior is opt in, as in ``tag`` must be present,
  with opt-out: true, the tag doesn't need to be present.

The reason we filter for only seeing instances older than 1 hour, if a dev is on a VM that is shut down by the off hours schedule, and they turn it back on, if we run custodian again we don't want to keep shutting down the VM on the dev repeatedly.

.. code-block:: yaml

   policies:
     - name: stop-after-hours
       resource: ec2
       filters:
         - type: offhour
           tag: StopAfterHours
           default_tz: pt
         - type: instance-age
           hours: 1
       actions:
         - stop
   
     - name: start-after-hours
       resource: ec2
       filters:
         - type: onhour
           tag: StartAfterHours
           default_tz: pt
           onhour: 12
         - type: value
           value: 1
           key: LaunchTime
           op: less-than
           value_type: age
       actions:
         - start