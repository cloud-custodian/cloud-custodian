.. _amigarbagecollect:

ami - deregister old unused AMIs (and delete the associated snapshots)
======================================================================

The following example policy will deregister AMIs older than 30 days that don't have Preferred=True tag and are unused. Unused is defined in the ImageUnusedFilter class in ami.py. Basically if the AMI isn't used in an ASG, LaunchConfig or EC2 instance, it is unused. It's also note worthy, that in addition to the AMI being deregistered, all snapshots associated with the AMI are deleted and the manifest and s3 files are removed (if it's an instance backed storage) if you set the delete_source option to true (which is optional).

.. code-block:: yaml

   policies:
   - name: ami-unused
     resource: ami
     filters:
       - type: value
         key: tag:Preferred
         op: not-equal
         value: 'true'
       - type: unused
         value: true
       - type: image-age
         days: 30
         op: gt
     actions:
       - type: deregister
         delete_source: true