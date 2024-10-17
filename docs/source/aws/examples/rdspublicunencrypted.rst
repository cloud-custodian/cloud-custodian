RDS - Terminate Unencrypted Public Instances
============================================

.. code-block:: yaml

  policies:
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
     actions:
       - type: delete
         skip-snapshot: true

