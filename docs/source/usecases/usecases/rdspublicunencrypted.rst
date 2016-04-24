RDS - Terminate Unencrypted Public Instances
============================================

.. code-block:: yaml

   - name: terminate-unencrypted-public-rds
     description: |
       Terminate all unencrypted or publicly available RDS upon creation
     resource: rds
     mode:
       type: cloudtrail
       events:
         - CreateDBInstance
     filters:
       - or:
           - StorageEncrypted: false
           - PubliclyAccessible: true
           # matches true if RDS in default VPC
           - type: default-vpc
     actions:
       - type: delete
         skip-snapshot: true

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
