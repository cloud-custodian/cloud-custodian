lambda policies to autotag resources with username and full principal id
========================================================================

.. code:: yaml

 policies:

 - name: auto-tag-redshift
   description: |
     Autotags any newly created redshift clusters
   resource: redshift
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - CreateCluster
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-rds
   description: |
     Autotags any newly created rds instances
   resource: rds
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: rds.amazonaws.com
         event: CreateDBInstance
         ids: "requestParameters.dBInstanceIdentifier"
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id


.. code:: yaml

 policies:
 - name: auto-tag-rds-snapshot
   description: |
     Autotags any newly created rds-snapshots
   resource: rds-snapshot
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: rds.amazonaws.com
         event: CreateDBSnapshot
         ids: "requestParameters.dBSnapshotIdentifier"
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-rds-cluster
   description: |
     Autotags any newly created rds-cluster instances
   resource: rds-cluster
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: rds.amazonaws.com
         event: CreateDBCluster
         ids: "requestParameters.dBClusterIdentifier"
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-lambda
   description: |
     Autotags any newly created lambda functions
   resource: lambda
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: lambda.amazonaws.com
         event: CreateFunction20150331
         ids: "responseElements.functionName"
   actions:
   - type: auto-tag-user
     tag: auto:tagging:creator-name
     full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-eni
   description: |
     Autotags any newly created enis
   resource: eni
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: ec2.amazonaws.com
         event: CreateNetworkInterface
         ids: "responseElements.networkInterface.networkInterfaceId"
   actions:
    - type: auto-tag-user
      tag: auto:tagging:creator-name
      full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-elb
   description: |
     Autotags any newly created ELBs
   resource: elb
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - CreateLoadBalancer
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 
 - name: auto-tag-elasticsearch
   description: |
     Autotags any newly created elasticsearch domain
   resource: elasticsearch
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - CreateElasticsearchDomain
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 
 - name: auto-tag-dynamodb-table
   description: |
     Autotags any newly created dynamodb-table clusters
   resource: dynamodb-table
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - CreateTable
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 
 - name: auto-tag-cache-cluster
   description: |
     Autotags any newly created cache-cluster domain
   resource: cache-cluster
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - Createcache-clusterDomain
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id

.. code:: yaml

 policies:
 - name: auto-tag-app-elb
   description: |
     Autotags any newly created ELBs
   resource: app-elb
   mode:
     type: cloudtrail
     role: arn:aws:iam::{account_id}:role/custodian-auto-tag-lambda
     events:
       - source: elasticloadbalancing.amazonaws.com
         event: CreateLoadBalancer
         ids: "requestParameters.name"
   actions:
     - type: auto-tag-user
       tag: auto:tagging:creator-name
       full_principal_id_tag: auto:tagging:creator-id
