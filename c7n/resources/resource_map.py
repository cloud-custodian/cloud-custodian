# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
ResourceMap = {
  "aws.access-analyzer-finding": "c7n.resources.accessanalyzer.AccessanalyzerFinding",
  "aws.account": "c7n.resources.account.Account",
  "aws.acm-certificate": "c7n.resources.acm.Certificate",
  "aws.advisor-check": "c7n.resources.support.AdvisorCheck",
  "aws.airflow": "c7n.resources.airflow.ApacheAirflow",
  "aws.alarm": "c7n.resources.cw.Alarm",
  "aws.ami": "c7n.resources.ami.AMI",
  "aws.apigw-domain-name": "c7n.resources.apigw.CustomDomainName",
  "aws.apigwv2": "c7n.resources.apigw.ApiGwV2",
  "aws.apigwv2-stage": "c7n.resources.apigw.ApiGatewayV2Stage",
  "aws.appmesh-mesh": "c7n.resources.appmesh.AppmeshMesh",
  "aws.appmesh-virtualgateway": "c7n.resources.appmesh.AppmeshVirtualGateway",
  "aws.appmesh-virtual-gateway": "c7n.resources.appmesh.AppmeshVirtualGateway",
  "aws.appmesh-virtualnode": "c7n.resources.appmesh.AppmeshVirtualNode",
  "aws.app-elb": "c7n.resources.appelb.AppELB",
  "aws.app-elb-target-group": "c7n.resources.appelb.AppELBTargetGroup",
  "aws.app-flow": "c7n.resources.appflow.AppFlow",
  "aws.appdiscovery-agent": "c7n.resources.discovery.AppdiscoveryAgent",
  "aws.appstream-fleet": "c7n.resources.appstream.AppStreamFleet",
  "aws.appstream-stack": "c7n.resources.appstream.AppStreamStack",
  "aws.artifact-domain": "c7n.resources.artifact.ArtifactDomain",
  "aws.artifact-repo": "c7n.resources.artifact.ArtifactRepo",
  "aws.asg": "c7n.resources.asg.ASG",
  "aws.athena-named-query": "c7n.resources.athena.AthenaNamedQuery",
  "aws.backup-plan": "c7n.resources.backup.BackupPlan",
  "aws.backup-vault": "c7n.resources.backup.BackupVault",
  "aws.batch-compute": "c7n.resources.batch.ComputeEnvironment",
  "aws.batch-definition": "c7n.resources.batch.JobDefinition",
  "aws.batch-queue": "c7n.resources.batch.BatchJobQueue",
  "aws.bedrock-agent": "c7n.resources.bedrock.BedrockAgent",
  "aws.bedrock-custom-model": "c7n.resources.bedrock.BedrockCustomModel",
  "aws.bedrock-knowledge-base": "c7n.resources.bedrock.BedrockKnowledgeBase",
  "aws.budget": "c7n.resources.budgets.Budget",
  "aws.cache-cluster": "c7n.resources.elasticache.ElastiCacheCluster",
  "aws.cache-snapshot": "c7n.resources.elasticache.ElastiCacheSnapshot",
  "aws.cache-subnet-group": "c7n.resources.elasticache.ElastiCacheSubnetGroup",
  "aws.catalog-portfolio": "c7n.resources.servicecatalog.CatalogPortfolio",
  "aws.catalog-product": "c7n.resources.servicecatalog.CatalogProduct",
  "aws.cfn": "c7n.resources.cfn.CloudFormation",
  "aws.cloud-directory": "c7n.resources.directory.CloudDirectory",
  "aws.cloudhsm-cluster": "c7n.resources.hsm.CloudHSMCluster",
  "aws.cloudsearch": "c7n.resources.cloudsearch.CloudSearch",
  "aws.cloudtrail": "c7n.resources.cloudtrail.CloudTrail",
  "aws.cloudwatch-dashboard": "c7n.resources.cw.CloudWatchDashboard",
  "aws.codebuild": "c7n.resources.code.CodeBuildProject",
  "aws.codebuild-source-credentials": "c7n.resources.code.CodeBuildSourceCredentials",
  "aws.codecommit": "c7n.resources.code.CodeRepository",
  "aws.codedeploy-app": "c7n.resources.code.CodeDeployApplication",
  "aws.codedeploy-deployment": "c7n.resources.code.CodeDeployDeployment",
  "aws.codedeploy-group": "c7n.resources.code.CodeDeployDeploymentGroup",
  "aws.codepipeline": "c7n.resources.code.CodeDeployPipeline",
  "aws.composite-alarm": "c7n.resources.cw.CompositeAlarm",
  "aws.config-recorder": "c7n.resources.config.ConfigRecorder",
  "aws.config-rule": "c7n.resources.config.ConfigRule",
  "aws.connect-campaign": "c7n.resources.connect.ConnectCampaign",
  "aws.connect-instance": "c7n.resources.connect.Connect",
  "aws.customer-gateway": "c7n.resources.vpc.CustomerGateway",
  "aws.datalake-location": "c7n.resources.lakeformation.LakeFormationRegisteredLocation",
  "aws.datapipeline": "c7n.resources.datapipeline.DataPipeline",
  "aws.datasync-agent": "c7n.resources.datasync.DataSyncAgent",
  "aws.datasync-task": "c7n.resources.datasync.DataSyncTask",
  "aws.dax": "c7n.resources.dynamodb.DynamoDbAccelerator",
  "aws.devicefarm-project": "c7n.resources.devicefarm.DevicefarmProject",
  "aws.directconnect": "c7n.resources.directconnect.DirectConnect",
  "aws.directory": "c7n.resources.directory.Directory",
  "aws.distribution": "c7n.resources.cloudfront.Distribution",
  "aws.dlm-policy": "c7n.resources.dlm.DLMPolicy",
  "aws.dms-endpoint": "c7n.resources.dms.DmsEndpoints",
  "aws.dms-instance": "c7n.resources.dms.ReplicationInstance",
  "aws.dms-replication-task": "c7n.resources.dms.DMSReplicationTask",
  "aws.dynamodb-backup": "c7n.resources.dynamodb.Backup",
  "aws.dynamodb-stream": "c7n.resources.dynamodb.Stream",
  "aws.dynamodb-table": "c7n.resources.dynamodb.Table",
  "aws.ebs": "c7n.resources.ebs.EBS",
  "aws.ebs-snapshot": "c7n.resources.ebs.Snapshot",
  "aws.ec2": "c7n.resources.ec2.EC2",
  "aws.ec2-host": "c7n.resources.ec2.DedicatedHost",
  "aws.ec2-reserved": "c7n.resources.ec2.ReservedInstance",
  "aws.ec2-spot-fleet-request": "c7n.resources.ec2.SpotFleetRequest",
  "aws.ec2-capacity-reservation": "c7n.resources.ec2.CapacityReservation",
  "aws.ecr": "c7n.resources.ecr.ECR",
  "aws.ecr-image": "c7n.resources.ecr.RepositoryImage",
  "aws.ecs": "c7n.resources.ecs.ECSCluster",
  "aws.ecs-container-instance": "c7n.resources.ecs.ContainerInstance",
  "aws.ecs-service": "c7n.resources.ecs.Service",
  "aws.ecs-task": "c7n.resources.ecs.Task",
  "aws.ecs-task-definition": "c7n.resources.ecs.TaskDefinition",
  "aws.efs": "c7n.resources.efs.ElasticFileSystem",
  "aws.efs-mount-target": "c7n.resources.efs.ElasticFileSystemMountTarget",
  "aws.eks": "c7n.resources.eks.EKS",
  "aws.eks-nodegroup": "c7n.resources.eks.NodeGroup",
  "aws.elastic-ip": "c7n.resources.vpc.NetworkAddress",
  "aws.elasticache-group": "c7n.resources.elasticache.ElastiCacheReplicationGroup",
  "aws.elasticbeanstalk": "c7n.resources.elasticbeanstalk.ElasticBeanstalk",
  "aws.elasticbeanstalk-environment": "c7n.resources.elasticbeanstalk.ElasticBeanstalkEnvironment",
  "aws.elasticsearch": "c7n.resources.elasticsearch.ElasticSearchDomain",
  "aws.elasticsearch-reserved": "c7n.resources.elasticsearch.ReservedInstances",
  "aws.elb": "c7n.resources.elb.ELB",
  "aws.emr": "c7n.resources.emr.EMRCluster",
  "aws.emr-security-configuration": "c7n.resources.emr.EMRSecurityConfiguration",
  "aws.emr-serverless-app": "c7n.resources.emr.EMRServerless",
  "aws.eni": "c7n.resources.vpc.NetworkInterface",
  "aws.event-bus": "c7n.resources.cw.EventBus",
  "aws.event-rule": "c7n.resources.cw.EventRule",
  "aws.event-rule-target": "c7n.resources.cw.EventRuleTarget",
  "aws.firehose": "c7n.resources.kinesis.DeliveryStream",
  "aws.firewall": "c7n.resources.firewall.NetworkFirewall",
  "aws.fis-experiment": "c7n.resources.fis.Experiment",
  "aws.fis-template": "c7n.resources.fis.ExperimentTemplate",
  "aws.flow-log": "c7n.resources.vpc.FlowLog",
  "aws.fsx": "c7n.resources.fsx.FSx",
  "aws.fsx-backup": "c7n.resources.fsx.FSxBackup",
  "aws.gamelift-build": "c7n.resources.gamelift.GameLiftBuild",
  "aws.gamelift-fleet": "c7n.resources.gamelift.GameLiftFleet",
  "aws.glacier": "c7n.resources.glacier.Glacier",
  "aws.glue-catalog": "c7n.resources.glue.GlueDataCatalog",
  "aws.glue-classifier": "c7n.resources.glue.GlueClassifier",
  "aws.glue-connection": "c7n.resources.glue.GlueConnection",
  "aws.glue-crawler": "c7n.resources.glue.GlueCrawler",
  "aws.glue-database": "c7n.resources.glue.GlueDatabase",
  "aws.glue-dev-endpoint": "c7n.resources.glue.GlueDevEndpoint",
  "aws.glue-job": "c7n.resources.glue.GlueJob",
  "aws.glue-ml-transform": "c7n.resources.glue.GlueMLTransform",
  "aws.glue-security-configuration": "c7n.resources.glue.GlueSecurityConfiguration",
  "aws.glue-table": "c7n.resources.glue.GlueTable",
  "aws.glue-trigger": "c7n.resources.glue.GlueTrigger",
  "aws.glue-workflow": "c7n.resources.glue.GlueWorkflow",
  "aws.graphql-api": "c7n.resources.appsync.GraphQLApi",
  "aws.guardduty-finding": "c7n.resources.guardduty.GuarddutyFinding",
  "aws.health-event": "c7n.resources.health.HealthEvents",
  "aws.healthcheck": "c7n.resources.route53.HealthCheck",
  "aws.hostedzone": "c7n.resources.route53.HostedZone",
  "aws.hsm": "c7n.resources.hsm.CloudHSM",
  "aws.hsm-client": "c7n.resources.hsm.HSMClient",
  "aws.hsm-hapg": "c7n.resources.hsm.PartitionGroup",
  "aws.iam-certificate": "c7n.resources.iam.ServerCertificate",
  "aws.iam-group": "c7n.resources.iam.Group",
  "aws.iam-oidc-provider": "c7n.resources.iam.OpenIdProvider",
  "aws.iam-policy": "c7n.resources.iam.Policy",
  "aws.iam-profile": "c7n.resources.iam.InstanceProfile",
  "aws.iam-role": "c7n.resources.iam.Role",
  "aws.iam-saml-provider": "c7n.resources.iam.SamlProvider",
  "aws.iam-user": "c7n.resources.iam.User",
  "aws.identity-pool": "c7n.resources.cognito.CognitoIdentityPool",
  "aws.insight-rule": "c7n.resources.cw.InsightRule",
  "aws.inspector2-finding": "c7n.resources.inspector2.Inspector2Finding",
  "aws.internet-gateway": "c7n.resources.vpc.InternetGateway",
  "aws.iot": "c7n.resources.iot.IoT",
  "aws.kafka": "c7n.resources.kafka.Kafka",
  "aws.key-pair": "c7n.resources.vpc.KeyPair",
  "aws.kinesis": "c7n.resources.kinesis.KinesisStream",
  "aws.kinesis-analytics": "c7n.resources.kinesis.AnalyticsApp",
  "aws.kinesis-analyticsv2": "c7n.resources.kinesis.KinesisAnalyticsAppV2",
  "aws.kinesis-video": "c7n.resources.kinesis.KinesisVideoStream",
  "aws.kms": "c7n.resources.kms.KeyAlias",
  "aws.kms-key": "c7n.resources.kms.Key",
  "aws.lambda": "c7n.resources.awslambda.AWSLambda",
  "aws.lambda-layer": "c7n.resources.awslambda.LambdaLayerVersion",
  "aws.launch-config": "c7n.resources.asg.LaunchConfig",
  "aws.launch-template-version": "c7n.resources.ec2.LaunchTemplate",
  "aws.lex-bot": "c7n.resources.lex.LexBot",
  "aws.lightsail-db": "c7n.resources.lightsail.Database",
  "aws.lightsail-elb": "c7n.resources.lightsail.LoadBalancer",
  "aws.lightsail-instance": "c7n.resources.lightsail.Instance",
  "aws.log-group": "c7n.resources.cw.LogGroup",
  "aws.log-metric": "c7n.resources.cw.LogMetric",
  "aws.memorydb": "c7n.resources.memorydb.MemoryDb",
  "aws.memorydb-subnet-group": "c7n.resources.memorydb.MemoryDbSubnetGroup",
  "aws.message-broker": "c7n.resources.mq.MessageBroker",
  "aws.message-config": "c7n.resources.mq.MessageConfig",
  "aws.mirror-session": "c7n.resources.vpc.TrafficMirrorSession",
  "aws.bedrock-customization-job": "c7n.resources.bedrock.BedrockModelCustomizationJob",
  "aws.mirror-target": "c7n.resources.vpc.TrafficMirrorTarget",
  "aws.ml-model": "c7n.resources.ml.MLModel",
  "aws.nat-gateway": "c7n.resources.vpc.NATGateway",
  "aws.network-acl": "c7n.resources.vpc.NetworkAcl",
  "aws.network-addr": "c7n.resources.vpc.NetworkAddress",
  "aws.opensearch-serverless": "c7n.resources.opensearch.OpensearchServerless",
  "aws.ops-item": "c7n.resources.ssm.OpsItem",
  "aws.opswork-cm": "c7n.resources.opsworks.OpsworksCM",
  "aws.opswork-stack": "c7n.resources.opsworks.OpsworkStack",
  "aws.org-account": "c7n.resources.org.OrgAccount",
  "aws.org-policy": "c7n.resources.org.OrgPolicy",
  "aws.org-unit": "c7n.resources.org.OrgUnit",
  "aws.peering-connection": "c7n.resources.vpc.PeeringConnection",
  "aws.pinpoint-app": "c7n.resources.pinpoint.PinpointApp",
  "aws.prefix-list": "c7n.resources.vpc.PrefixList",
  "aws.qldb": "c7n.resources.qldb.QLDB",
  "aws.quicksight-group": "c7n.resources.quicksight.QuicksightGroup",
  "aws.quicksight-user": "c7n.resources.quicksight.QuicksightUser",
  "aws.r53domain": "c7n.resources.route53.Route53Domain",
  "aws.rds": "c7n.resources.rds.RDS",
  "aws.rds-cluster": "c7n.resources.rdscluster.RDSCluster",
  "aws.rds-cluster-param-group": "c7n.resources.rdsparamgroup.RDSClusterParamGroup",
  "aws.rds-cluster-snapshot": "c7n.resources.rdscluster.RDSClusterSnapshot",
  "aws.rds-param-group": "c7n.resources.rdsparamgroup.RDSParamGroup",
  "aws.rds-proxy": "c7n.resources.rds.RDSProxy",
  "aws.rds-reserved": "c7n.resources.rds.ReservedRDS",
  "aws.rds-snapshot": "c7n.resources.rds.RDSSnapshot",
  "aws.rds-subnet-group": "c7n.resources.rds.RDSSubnetGroup",
  "aws.rds-subscription": "c7n.resources.rds.RDSSubscription",
  "aws.readiness-check": "c7n.resources.route53.ReadinessCheck",
  "aws.recovery-cluster": "c7n.resources.route53.RecoveryCluster",
  "aws.recovery-control-panel": "c7n.resources.route53.ControlPanel",
  "aws.redshift": "c7n.resources.redshift.Redshift",
  "aws.redshift-reserved": "c7n.resources.redshift.ReservedNode",
  "aws.redshift-snapshot": "c7n.resources.redshift.RedshiftSnapshot",
  "aws.redshift-subnet-group": "c7n.resources.redshift.RedshiftSubnetGroup",
  "aws.resolver-logs": "c7n.resources.route53.ResolverQueryLogConfig",
  "aws.rest-account": "c7n.resources.apigw.RestAccount",
  "aws.rest-api": "c7n.resources.apigw.RestApi",
  "aws.rest-client-certificate": "c7n.resources.apigw.RestClientCertificate",
  "aws.rest-resource": "c7n.resources.apigw.RestResource",
  "aws.rest-stage": "c7n.resources.apigw.RestStage",
  "aws.rest-vpclink": "c7n.resources.apigw.RestApiVpcLink",
  "aws.route-table": "c7n.resources.vpc.RouteTable",
  "aws.rrset": "c7n.resources.route53.ResourceRecordSet",
  "aws.s3": "c7n.resources.s3.S3",
  "aws.s3-directory": "c7n.resources.s3.S3Directory",
  "aws.s3-access-point": "c7n.resources.s3control.AccessPoint",
  "aws.s3-access-point-multi": "c7n.resources.s3control.MultiRegionAccessPoint",
  "aws.s3-storage-lens": "c7n.resources.s3control.StorageLens",
  "aws.sagemaker-auto-ml-job": "c7n.resources.sagemaker.SagemakerAutoMLJob",
  "aws.sagemaker-cluster": "c7n.resources.sagemaker.Cluster",
  "aws.sagemaker-compilation-job": "c7n.resources.sagemaker.SagemakerCompilationJob",
  "aws.sagemaker-data-quality-job-definition":
    "c7n.resources.sagemaker.SagemakerDataQualityJobDefinition",
  "aws.sagemaker-domain": "c7n.resources.sagemaker.SagemakerDomain",
  "aws.sagemaker-endpoint": "c7n.resources.sagemaker.SagemakerEndpoint",
  "aws.sagemaker-endpoint-config": "c7n.resources.sagemaker.SagemakerEndpointConfig",
  "aws.sagemaker-model-explainability-job-definition":
    "c7n.resources.sagemaker.SagemakerModelExplainabilityJobDefinition",
  "aws.sagemaker-model-quality-job-definition":
    "c7n.resources.sagemaker.SagemakerModelQualityJobDefinition",
  "aws.sagemaker-processing-job": "c7n.resources.sagemaker.SagemakerProcessingJob",
  "aws.sagemaker-job": "c7n.resources.sagemaker.SagemakerJob",
  "aws.sagemaker-model": "c7n.resources.sagemaker.Model",
  "aws.sagemaker-notebook": "c7n.resources.sagemaker.NotebookInstance",
  "aws.sagemaker-transform-job": "c7n.resources.sagemaker.SagemakerTransformJob",
  "aws.sagemaker-hyperparameter-tuning-job":
    "c7n.resources.sagemaker.SagemakerHyperParameterTuningJob",
  "aws.sagemaker-model-bias-job-definition":
    "c7n.resources.sagemaker.SagemakerModelBiasJobDefinition",
  "aws.scaling-policy": "c7n.resources.asg.ScalingPolicy",
  "aws.secrets-manager": "c7n.resources.secretsmanager.SecretsManager",
  "aws.security-group": "c7n.resources.vpc.SecurityGroup",
  "aws.securityhub-finding": "c7n.resources.securityhub.SecurityhubFinding",
  "aws.serverless-app": "c7n.resources.sar.ServerlessApp",
  "aws.service-quota": "c7n.resources.quotas.ServiceQuota",
  "aws.service-quota-request": "c7n.resources.quotas.ServiceQuotaRequest",
  "aws.ses-configuration-set": "c7n.resources.ses.SESConfigurationSet",
  "aws.ses-email-identity": "c7n.resources.ses.SESEmailIdentity",
  "aws.ses-receipt-rule-set": "c7n.resources.ses.SESReceiptRuleSet",
  "aws.shield-attack": "c7n.resources.shield.ShieldAttack",
  "aws.shield-protection": "c7n.resources.shield.ShieldProtection",
  "aws.simpledb": "c7n.resources.simpledb.SimpleDB",
  "aws.snowball": "c7n.resources.snowball.Snowball",
  "aws.snowball-cluster": "c7n.resources.snowball.SnowballCluster",
  "aws.sns": "c7n.resources.sns.SNS",
  "aws.sns-subscription": "c7n.resources.sns.SNSSubscription",
  "aws.sqs": "c7n.resources.sqs.SQS",
  "aws.ssm-activation": "c7n.resources.ssm.SSMActivation",
  "aws.ssm-data-sync": "c7n.resources.ssm.SSMDataSync",
  "aws.ssm-document": "c7n.resources.ssm.SSMDocument",
  "aws.ssm-managed-instance": "c7n.resources.ssm.ManagedInstance",
  "aws.ssm-parameter": "c7n.resources.ssm.SSMParameter",
  "aws.ssm-patch-group": "c7n.resources.ssm.SsmPatchGroup",
  "aws.ssm-session-manager": "c7n.resources.ssm.SSMSessionManager",
  "aws.step-machine": "c7n.resources.sfn.StepFunction",
  "aws.storage-gateway": "c7n.resources.storagegw.StorageGateway",
  "aws.streaming-distribution": "c7n.resources.cloudfront.StreamingDistribution",
  "aws.subnet": "c7n.resources.vpc.Subnet",
  "aws.support-case": "c7n.resources.support.SupportCase",
  "aws.swf-domain": "c7n.resources.swf.SimpleWorkflowDomain",
  "aws.timestream-database": "c7n.resources.timestream.TimestreamDatabase",
  "aws.timestream-table": "c7n.resources.timestream.TimestreamTable",
  "aws.transfer-server": "c7n.resources.transfer.TransferServer",
  "aws.transfer-user": "c7n.resources.transfer.TransferUser",
  "aws.transit-attachment": "c7n.resources.vpc.TransitGatewayAttachment",
  "aws.transit-gateway": "c7n.resources.vpc.TransitGateway",
  "aws.user-pool": "c7n.resources.cognito.CognitoUserPool",
  "aws.vpc": "c7n.resources.vpc.Vpc",
  "aws.vpc-endpoint": "c7n.resources.vpc.VpcEndpoint",
  "aws.vpn-connection": "c7n.resources.vpc.VPNConnection",
  "aws.vpn-gateway": "c7n.resources.vpc.VPNGateway",
  "aws.waf": "c7n.resources.waf.WAF",
  "aws.waf-regional": "c7n.resources.waf.RegionalWAF",
  "aws.wafv2": "c7n.resources.waf.WAFV2",
  "aws.workspaces": "c7n.resources.workspaces.Workspace",
  "aws.workspaces-bundle": "c7n.resources.workspaces.WorkspacesBundle",
  "aws.workspaces-directory": "c7n.resources.workspaces.WorkspaceDirectory",
  "aws.workspaces-image": "c7n.resources.workspaces.WorkspaceImage",
  "aws.workspaces-web": "c7n.resources.workspaces.WorkspacesWeb",
  "aws.xray-group": "c7n.resources.xray.XRayGroup",
  "aws.xray-rule": "c7n.resources.xray.XRaySamplingRule"
}
