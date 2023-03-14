.. _blocknonstandardregionresources:

Block New Resources In Non-Standard Regions
=====================================================

The following are examples of Cloud Custodian policies which detect the region
a resource is being launched in and deletes the resource if it's outside your standard
approved regions.  These examples block the full creation of the resources launched outside
of the us-east-1 and eu-west-1 regions and then emails the event-owner
(the person launching the resource) and the Cloud Team.  This set of policies covers several
of the common AWS services but you may add your desired services if supported by Cloud Custodian.
While a proactive approach through IAM or AWS Organizations policies is the ideal way to go, that
isn't always possible or manageable for all users.  These policies take a reactive approach and may
be a fitting use case for some users.
For the notify action to work you will need to have installed and configured the Cloud Custodian
c7n-mailer tool.




.. code-block:: yaml

		policies:

		- name: ec2-terminate-non-standard-region
		  resource: ec2
		  description: |
			Any EC2 instance launched in a non standard region outside
			of us-east-1 and eu-west-1 will be terminated
		  mode:
			type: cloudtrail
			events:
			  - RunInstances
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: terminate
			  force: true
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "EC2 SERVER TERMINATED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new EC2 server has been terminated.  Please relaunch the
			  server in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: asg-terminate-non-standard-region
		  resource: asg
		  mode:
			  type: cloudtrail
			  events:
				- source: autoscaling.amazonaws.com
				  event: CreateAutoScalingGroup
				  ids: requestParameters.autoScalingGroupName
		  description: |
			  Detect when a new AutoScaling Group is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			  force: true
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "ASG TERMINATED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new ASG has been terminated.  Please relaunch the
			  ASG in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1

				

		- name: app-elb-terminate-non-standard-region
		  resource: app-elb
		  mode:
			  type: cloudtrail
			  events:
				- source: "elasticloadbalancing.amazonaws.com"
				  event: CreateLoadBalancer
				  ids: "requestParameters.name"
		  description: |
			  Detect when a new Application Load Balancer Group is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "App ELB TERMINATED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new App ELB has been deleted.  Please relaunch the
			  App ELB in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: elb-terminate-non-standard-region
		  resource: elb
		  mode:
			type: cloudtrail
			events:
			   - CreateLoadBalancer
		  description: |
			  Detect when a new Load Balancer is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "ELB TERMINATED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new ELB has been deleted.  Please relaunch the
			  ELB in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: es-terminate-non-standard-region
		  resource: elasticsearch
		  mode:
			type: cloudtrail
			events:
				- CreateElasticsearchDomain
		  description: |
			  Detect when a new Elasticsearch Domain is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "ES DOMAIN TERMINATED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Elasticsearch Domain has been deleted.  Please relaunch the
			  Domain in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: lambda-terminate-non-standard-region
		  resource: lambda
		  mode:
			type: cloudtrail
			events:
				- source: lambda.amazonaws.com
				  event: CreateFunction20150331
				  ids: "requestParameters.functionName"
		  description: |
			  Detect when a new Lambda Function is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
			- not:
				- or:
					- type: value
					  key: FunctionName
					  op: regex
					  value: ^(custodian?)\w+
		  actions:
			- delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "LAMBDA DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Lambda Function has been deleted.  Please relaunch
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: rds-terminate-non-standard-region
		  resource: rds
		  mode:
			 type: cloudtrail
			 events:
				- source: rds.amazonaws.com
				  event: CreateDBInstance
				  ids: "requestParameters.dBInstanceIdentifier"
		  description: |
			  Detect when a new RDS is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			  skip-snapshot: true
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "RDS DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new RDS Database has been deleted.  Please relaunch
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: rdscluster-terminate-non-standard-region
		  resource: rds-cluster
		  mode:
			type: cloudtrail
			events:
			  - CreateCluster
		  description: |
			  Detect when a new RDS Cluster is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			  skip-snapshot: true
			  delete-instances: true
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "RDS CLUSTER DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new RDS Database Cluster has been deleted.  Please relaunch
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: sg-terminate-non-standard-region
		  resource: security-group
		  mode:
			  type: cloudtrail
			  events:
				- source: ec2.amazonaws.com
				  event: CreateSecurityGroup
				  ids: "responseElements.groupId"
		  description: |
			  Detect when a new Security Group is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "SG DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Security Group has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: ami-terminate-non-standard-region
		  resource: ami
		  mode:
			type: cloudtrail
			events:
				- source: "ec2.amazonaws.com"
				  event: "CreateImage"
				  ids: "responseElements.imageId"
		  description: |
			  Detect when a new Amazon Machine Image is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- deregister
			- remove-launch-permissions
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "AMI DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Amazon Machine Image has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: s3-terminate-non-standard-region
		  resource: s3
		  mode:
			type: cloudtrail
			events:
			  - CreateBucket
			role: arn:aws:iam::{account_id}:role/Cloud_Custodian_Role
			timeout: 200
		  description: |
			  Detect when a new S3 Bucket is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			  remove-contents: true
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "S3 DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new S3 Bucket has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: dynamo-terminate-non-standard-region
		  resource: dynamodb-table
		  mode:
			type: cloudtrail
			events:
			  - CreateTable
		  description: |
			  Detect when a new DynamoDB Table is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "DYNAMODB DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new DynamoDB Table has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: kinesis-terminate-non-standard-region
		  resource: kinesis
		  mode:
			type: cloudtrail
			events:
				- source: "kinesis.amazonaws.com"
				  event: "CreateStream"
				  ids: "requestParameters.streamName"
		  description: |
			  Detect when a new Kinesis Stream is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "KINESIS DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Kinesis Stream has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1



		- name: firehose-terminate-non-standard-region
		  resource: firehose
		  mode:
			type: cloudtrail
			events:
				- source: "firehose.amazonaws.com"
				  event: "CreateDeliveryStream"
				  ids: "requestParameters.deliveryStreamName"
		  description: |
			  Detect when a new Firehose is created in a non-standard
			  region and delete it and notify the customer
		  filters:
			- type: event
			  key: "detail.awsRegion"
			  op: not-in
			  value:
				  - us-east-1
				  - eu-west-1
		  actions:
			- type: delete
			- type: notify
			  template: default.html
			  priority_header: 1
			  subject: "FIREHOSE DELETED - Non-Standard Region [custodian {{ account }} - {{ region }}]" 
			  violation_desc: "Launching resources outside of the standard regions is prohibited"
			  action_desc: "Actions Taken:  Your new Firehose has been deleted.  Please recreate
			  in your accounts standard region which is either eu-west-1 or us-east-1."
			  to:
				- CloudTeam@Company.com
				- event-owner
			  transport:
				type: sqs
				queue: https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXX/cloud-custodian-mailer
				region: us-east-1
