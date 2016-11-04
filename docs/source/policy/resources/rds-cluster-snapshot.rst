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
            value: 'test-restore'
        actions:
          - type: restore
            vpc-security-groups:
            - 'sg-8483djk3'
            port:
              3999
            snapshot-identifier:
              'my optional db snapshot identifier'
            db-security-group-name:
              'my security group'
            db-instances:
              identifier:
                test-restore
              id-suffix:
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

Default Values

``vpc-security-groups``
    the vpc security group that you will want to use on your database instances/cluster
    default: AWS's Default VPC

``port``
    port for your database instances to use
    default: 3306

``snapshot-identifier``
    the snapshot used to restore the cluster
    default: the most recent snapshot taken

``db-security-group-name``
    the security group you want to have on your db instances
    default: aws default security group

``db-instances``
    REQUIRED
    the params for your db instances that are created from the cluster

    ``identifer``
        REQUIRED
        what you want to call your db prefixed.  i.e. - test-restore will be used for name

    ``id-suffix``
        the post fixed value after the identifier
        default: dev

    ``number``
        number of database instances to create.  With each additional database instance the database name will increment
        by 1
        default: 1

    ``size``
        the size of the instances you will use for your databases
        default: db.r3.large




