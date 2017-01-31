EBS - Delete Unencrypted
========================

.. code-block:: yaml

  policies:
     - name: terminate-unencrypted-ebs
       description: |
         Terminate all unencrypted EBS volumes upon creation
       resource: ebs
       mode:
         type: cloudtrail
         events:
           - CreateVolume
       filters:
         - Encrypted: false
       actions:
         - delete
