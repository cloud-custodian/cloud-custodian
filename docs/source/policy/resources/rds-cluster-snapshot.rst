.. _rds-cluster-snapshot:

Relational Database Service DB Cluster Snapshots (RDS DB Cluster Snapshots)
===========================================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days

Actions
-------

``delete``
  Delete DB cluster snapshot

``restore``
  Restore an RDS cluster to its latest snapshot.  Note:  You must supply policy correctly otherwise this will create a
  cluster and database instances with default configurations (ie - Default VPC Group).

Sample Policy for ``restore`` action

    policies:
      - name: rds-cluster-snapshot
        resource: rds-cluster-snapshot
        filters:
          - type: value
            key: "DBClusterIdentifier"
            value: ['test-restore']
            op: in
        actions:
          - type: restore
            vpc-security-groups:
            - 'sg-8483djk3'
            port:
              3999
            db-security-group-name:
              'my vpc security group'
            db-instances:
              identifier:
                test-restore
              post-fix:
                'qa'
              number:
                2
              size:
                'db.r3.large'


The following policy will create the following:
    1 RDS aurora cluster instance
    2 RDS database instances part of the cluster (1 being writer and 1 being read replica)
        Sized at r3.large instance (minimum size)
        Running on port 3999
        Database Identifiers will be: test-restore-qa and test-restore-qa-1
        Within the sg-8483djk3 VPC security group
        Within the group name ``my vpc security-group``

