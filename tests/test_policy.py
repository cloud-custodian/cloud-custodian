# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from datetime import datetime, timedelta
import json
import logging
import os
import shutil
import tempfile
from unittest import mock

from c7n import policy, manager
from c7n.config import Config
from c7n.provider import clouds
from c7n.exceptions import ResourceLimitExceeded, PolicyValidationError
from c7n.resources import aws, load_available
from c7n.resources.aws import AWS, Arn, fake_session
from c7n.resources.ec2 import EC2
from c7n.resources.kinesis import KinesisStream
from c7n.policy import execution, ConfigPollRuleMode, Policy, PullMode
from c7n.schema import generate, JsonSchemaValidator
from c7n.utils import dumps
from c7n.query import ConfigSource, TypeInfo
from c7n.version import version

from .common import BaseTest, event_data, Bag, load_data


class DummyResource(manager.ResourceManager):

    def resources(self):
        return [{"abc": 123}, {"def": 456}]

    @property
    def actions(self):

        class _a:

            def name(self):
                return self.f.__name__

            def __init__(self, f):
                self.f = f

            def process(self, resources):
                return self.f(resources)

        def p1(resources):
            return [{"abc": 456}, {"def": 321}]

        def p2(resources):
            return resources

        return [_a(p1), _a(p2)]


class PolicyMetaLint(BaseTest):

    def setUp(self):
        # we need to load all resources for the linting meta tests.
        load_available()

    def test_policy_missing_provider_session(self):
        self.assertRaises(
            RuntimeError,
            policy.get_session_factory,
            'nosuchthing', Bag())

    def test_policy_detail_spec_permissions(self):
        policy = self.load_policy(
            {"name": "kinesis-delete", "resource": "kinesis", "actions": ["delete"]}
        )
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            {
                "kinesis:DescribeStream",
                "kinesis:ListStreams",
                "kinesis:DeleteStream",
                "kinesis:ListTagsForStream",
                "tag:GetResources"
            },
        )

    def test_resource_type_repr_with_arn_type(self):
        policy = self.load_policy({'name': 'ecr', 'resource': 'aws.ops-item'})
        # check the repr absent a config type and cfn type but with an arn type
        assert policy.resource_manager.resource_type.config_type is None
        assert policy.resource_manager.resource_type.cfn_type is None
        assert str(policy.resource_manager.resource_type) == '<TypeInfo AWS::Ssm::Opsitem>'

    def test_resource_type_repr(self):
        policy = self.load_policy({'name': 'airflow', 'resource': 'aws.airflow'})
        # check the repr absent a config type but with a cfn type
        assert policy.resource_manager.resource_type.config_type is None
        assert str(policy.resource_manager.resource_type) == '<TypeInfo AWS::MWAA::Environment>'

    def test_schema_plugin_name_mismatch(self):
        # todo iterate over all clouds not just aws resources
        for k, v in manager.resources.items():
            for fname, f in v.filter_registry.items():
                if fname in ("or", "and", "not"):
                    continue
                self.assertIn(fname, f.schema["properties"]["type"]["enum"])
            for aname, a in v.action_registry.items():
                self.assertIn(aname, a.schema["properties"]["type"]["enum"])

    def test_schema(self):
        try:
            schema = generate()
            JsonSchemaValidator.check_schema(schema)
        except Exception:
            self.fail("Invalid schema")

    def test_schema_serialization(self):
        try:
            dumps(generate())
        except Exception:
            self.fail("Failed to serialize schema")

    def test_detail_spec_format(self):

        failed = []
        for k, v in manager.resources.items():
            detail_spec = getattr(v.resource_type, 'detail_spec', None)
            if not detail_spec:
                continue
            if not len(detail_spec) == 4:
                failed.append(k)
        if failed:
            self.fail(
                "%s resources have invalid detail_specs" % ", ".join(failed))

    def test_resource_augment_universal_mask(self):
        # universal tag had a potential bad patterm of masking
        # resource augmentation, scan resources to ensure
        missing = []
        for k, v in manager.resources.items():
            if not getattr(v.resource_type, "universal_taggable", None):
                continue
            if (
                v.augment.__name__ == "universal_augment" and
                getattr(v.resource_type, "detail_spec", None)
            ):
                missing.append(k)

        if missing:
            self.fail(
                "%s resource has universal augment masking resource augment" % (
                    ', '.join(missing))
            )

    def test_resource_universal_taggable_arn_type(self):
        missing = []
        for k, v in manager.resources.items():
            if not getattr(v, 'augment', None):
                continue
            if (
                v.augment.__name__ == "universal_augment" and
                    v.resource_type.arn_type is None
            ):
                missing.append(k)

        if missing:
            self.fail("%s universal taggable resource missing arn_type" % (
                ', '.join(missing)))

    def test_resource_shadow_source_augment(self):
        shadowed = []
        bad = []
        cfg = Config.empty()

        for k, v in manager.resources.items():
            if not getattr(v.resource_type, "config_type", None):
                continue

            p = Bag({"name": "permcheck", "resource": k, 'provider_name': 'aws'})
            ctx = self.get_context(config=cfg, policy=p)
            mgr = v(ctx, p)

            source = mgr.get_source("config")
            if not isinstance(source, ConfigSource):
                bad.append(k)

            if v.__dict__.get("augment"):
                shadowed.append(k)

        if shadowed:
            self.fail(
                "%s have resource managers shadowing source augments"
                % (", ".join(shadowed))
            )

        if bad:
            self.fail("%s have config types but no config source" % (", ".join(bad)))

    def test_resource_arn_override_generator(self):
        overrides = set()
        for k, v in manager.resources.items():
            arn_gen = bool(v.__dict__.get('get_arns') or v.__dict__.get('generate_arn'))

            if arn_gen:
                overrides.add(k)

        overrides = overrides.difference(
            {'account', 's3', 'hostedzone', 'log-group', 'rest-api', 'redshift-snapshot',
             'rest-stage', 'codedeploy-app', 'codedeploy-group', 'fis-template', 'dlm-policy',
             'apigwv2', 'apigwv2-stage', 'lexv2-bot-alias', 'apigw-domain-name', 'fis-experiment',
             'launch-template-version', 'glue-table', 'glue-catalog', 'cloudwatch-synthetics'})
        if overrides:
            raise ValueError("unknown arn overrides in %s" % (", ".join(overrides)))

    def test_resource_name(self):
        names = []
        for k, v in manager.resources.items():
            if not getattr(v.resource_type, "name", None):
                names.append(k)
        if names:
            self.fail("%s dont have resource name for reporting" % (", ".join(names)))

    def test_filter_spec(self):
        missing_fspec = []
        for k, v in manager.resources.items():
            if v.resource_type.filter_name is None:
                continue
            if not v.resource_type.filter_type:
                missing_fspec.append(k)
        if missing_fspec:
            self.fail('aws resources missing filter specs: %s' % (
                ', '.join(missing_fspec)))

    def test_ec2_id_prefix(self):
        missing_prefix = []
        for k, v in manager.resources.items():
            if v.resource_type.service != 'ec2':
                continue
            if v.resource_type.id_prefix is None:
                missing_prefix.append(k)
        if missing_prefix:
            self.fail('ec2 resources missing id prefix %s' % (', '.join(missing_prefix)))

    def test_cfn_resource_validity(self):
        # for resources which are annotated with cfn_type ensure that it is
        # a valid type.
        resource_cfn_types = set()
        for k, v in manager.resources.items():
            rtype = v.resource_type.cfn_type
            if rtype is not None:
                resource_cfn_types.add(rtype)
        cfn_types = set(load_data('cfn-types.json'))
        missing = set()
        for rtype in resource_cfn_types:
            if rtype not in cfn_types:
                missing.add(rtype)
        if missing:
            raise AssertionError("Bad cfn types:\n %s" % (
                "\n".join(sorted(missing))))

    def test_securityhub_resource_support(self):
        session = fake_session()._session
        model = session.get_service_model('securityhub')
        shape = model.shape_for('ResourceDetails')
        mangled_hub_types = set(shape.members.keys())
        resource_hub_types = set()

        whitelist = set(('AwsS3Object', 'Container'))
        todo = set((
            # q2 2025
            'CodeRepository',
            # q4 2023,
            'AwsEc2ClientVpnEndpoint',
            'AwsS3AccessPoint',
            'AwsMskCluster',
            'AwsEventsEventbus',
            'AwsEventsEndpoint',
            'AwsDmsReplicationTask',
            'AwsRoute53HostedZone',
            'AwsDmsEndpoint',
            'AwsDmsReplicationInstance',
            # q2 2023
            'AwsAthenaWorkGroup',
            'AwsStepFunctionStateMachine',
            'AwsGuardDutyDetector',
            'AwsAmazonMqBroker',
            'AwsAppSyncGraphQlApi',
            'AwsEventSchemasRegistry',
            "AwsEc2RouteTable",
            # q1 2023
            'AwsWafv2RuleGroup',
            'AwsWafv2WebAcl',
            'AwsEc2LaunchTemplate',
            'AwsSageMakerNotebookInstance',
            # q3 2022
            'AwsBackupBackupPlan',
            'AwsBackupBackupVault',
            'AwsBackupRecoveryPoint',
            'AwsCloudFormationStack',
            'AwsWafRegionalRule',
            'AwsWafRule',
            'AwsWafRuleGroup',
            'AwsKinesisStream',
            'AwsWafRegionalRuleGroup',
            'AwsEc2VpcPeeringConnection',
            'AwsWafRegionalWebAcl',
            'AwsCloudWatchAlarm',
            'AwsEfsAccessPoint',
            'AwsEc2TransitGateway',
            'AwsEcsContainer',
            'AwsEcsTask',
            'AwsBackupRecoveryPoint',
            # https://github.com/cloud-custodian/cloud-custodian/issues/7775
            'AwsBackupBackupPlan',
            'AwsBackupBackupVault',
            # q2 2022
            'AwsRdsDbSecurityGroup',
            # q1 2022
            'AwsNetworkFirewallRuleGroup',
            'AwsNetworkFirewallFirewall',
            'AwsNetworkFirewallFirewallPolicy',
            # q4 2021 - second wave
            'AwsXrayEncryptionConfig',
            'AwsOpenSearchServiceDomain',
            'AwsEc2VpcEndpointService',
            'AwsWafRateBasedRule',
            'AwsWafRegionalRateBasedRule',
            'AwsEcrRepository',
            'AwsEksCluster',
            # q4 2021
            'AwsEcrContainerImage',
            'AwsEc2VpnConnection',
            'AwsAutoScalingLaunchConfiguration',
            # q3 2021
            'AwsEcsService',
            'AwsRdsEventSubscription',
            # q2 2021
            'AwsEcsTaskDefinition',
            'AwsEcsCluster',
            'AwsEc2Subnet',
            'AwsElasticBeanstalkEnvironment',
            'AwsEc2NetworkAcl',
            # newer wave q1 2021,
            'AwsS3AccountPublicAccessBlock',
            'AwsSsmPatchCompliance',
            # newer wave q4 2020
            'AwsApiGatewayRestApi',
            'AwsApiGatewayStage',
            'AwsApiGatewayV2Api',
            'AwsApiGatewayV2Stage',
            'AwsCertificateManagerCertificate',
            'AwsCloudTrailTrail',
            'AwsElbLoadBalancer',
            'AwsIamGroup',
            'AwsRedshiftCluster',
            # newer wave q3 2020
            'AwsDynamoDbTable',
            'AwsEc2Eip',
            'AwsIamPolicy',
            'AwsIamUser',
            'AwsRdsDbCluster',
            'AwsRdsDbClusterSnapshot',
            'AwsRdsDbSnapshot',
            'AwsSecretsManagerSecret',
            # older wave
            'AwsElbv2LoadBalancer',
            'AwsEc2SecurityGroup',
            'AwsIamAccessKey',
            'AwsEc2NetworkInterface',
            'AwsWafWebAcl'))
        mangled_hub_types = mangled_hub_types.difference(whitelist).difference(todo)
        for k, v in manager.resources.items():
            finding = v.action_registry.get('post-finding')
            if finding:
                resource_hub_types.add(finding.resource_type)
        assert mangled_hub_types.difference(resource_hub_types) == set()

    def test_config_resource_support(self):

        # for several of these we express support as filter or action instead
        # of a resource.

        whitelist = {
            # q2 2025
            "AWS::AppConfig::ExtensionAssociation",
            "AWS::AppIntegrations::Application",
            "AWS::AppSync::ApiCache",
            "AWS::Bedrock::Guardrail",
            "AWS::Bedrock::KnowledgeBase",
            "AWS::Connect::Rule",
            "AWS::Connect::User",
            "AWS::EC2::ClientVpnTargetNetworkAssociation",
            "AWS::EC2::EIPAssociation",
            "AWS::EC2::InstanceConnectEndpoint",
            "AWS::EC2::IPAMResourceDiscovery",
            "AWS::EC2::IPAMResourceDiscoveryAssociation",
            "AWS::EC2::SnapshotBlockPublicAccess",
            "AWS::EC2::VPCBlockPublicAccessExclusion",
            "AWS::EC2::VPCBlockPublicAccessOptions",
            "AWS::EC2::VPCEndpointConnectionNotification",
            "AWS::EC2::VPNConnectionRoute",
            "AWS::Evidently::Segment",
            "AWS::InspectorV2::Activation",
            "AWS::MediaConnect::Gateway",
            "AWS::MSK::ClusterPolicy",
            "AWS::MSK::VpcConnection",
            "AWS::OpenSearchServerless::Collection",
            "AWS::OpenSearchServerless::VpcEndpoint",
            "AWS::Redshift::EndpointAuthorization",
            "AWS::Route53Profiles::Profile",
            "AWS::S3::StorageLensGroup",
            "AWS::S3Express::BucketPolicy",
            "AWS::S3Express::DirectoryBucket",
            "AWS::SageMaker::InferenceExperiment",
            "AWS::SecurityHub::Standard",
            "AWS::Transfer::Profile",
            # q1 2024
            "AWS::Cognito::UserPoolClient",
            "AWS::Cognito::UserPoolGroup",
            "AWS::EC2::NetworkInsightsAccessScope",
            "AWS::EC2::NetworkInsightsAnalysis",
            "AWS::Grafana::Workspace",
            "AWS::GroundStation::DataflowEndpointGroup",
            "AWS::ImageBuilder::ImageRecipe",
            "AWS::M2::Environment",
            "AWS::QuickSight::DataSource",
            "AWS::QuickSight::Template",
            "AWS::QuickSight::Theme",
            "AWS::RDS::OptionGroup",
            "AWS::Redshift::EndpointAccess",
            "AWS::Route53Resolver::FirewallRuleGroup",
            # q4 2023 wave 2 (aka reinvent)
            "AWS::ACMPCA::CertificateAuthorityActivation",
            "AWS::AppMesh::GatewayRoute",
            "AWS::Connect::Instance",
            "AWS::Connect::QuickConnect",
            "AWS::EC2::CarrierGateway",
            "AWS::EC2::IPAMPool",
            "AWS::EC2::TransitGatewayConnect",
            "AWS::EC2::TransitGatewayMulticastDomain",
            "AWS::ECS::CapacityProvider",
            "AWS::IAM::InstanceProfile",
            "AWS::IoT::CACertificate",
            "AWS::IoTTwinMaker::SyncJob",
            "AWS::KafkaConnect::Connector",
            "AWS::Lambda::CodeSigningConfig",
            "AWS::NetworkManager::ConnectPeer",
            "AWS::ResourceExplorer2::Index",
            # q4 2023
            "AWS::APS::RuleGroupsNamespace",
            "AWS::Batch::SchedulingPolicy",
            "AWS::CodeBuild::ReportGroup",
            "AWS::CodeGuruProfiler::ProfilingGroup",
            "AWS::InspectorV2::Filter",
            "AWS::IoT::JobTemplate",
            "AWS::IoT::ProvisioningTemplate",
            "AWS::IoTTwinMaker::ComponentType",
            "AWS::IoTWireless::FuotaTask",
            "AWS::IoTWireless::MulticastGroup",
            "AWS::MSK::BatchScramSecret",
            "AWS::MediaConnect::FlowSource",
            "AWS::Personalize::DatasetGroup",
            "AWS::Route53Resolver::ResolverQueryLoggingConfig",
            "AWS::Route53Resolver::ResolverQueryLoggingConfigAssociation",
            "AWS::SageMaker::FeatureGroup",
            "AWS::ServiceDiscovery::Instance",
            "AWS::Transfer::Certificate",
            # q3 2023
            "AWS::ACMPCA::CertificateAuthority",
            "AWS::Amplify::Branch",
            "AWS::AppConfig::HostedConfigurationVersion",
            "AWS::AppIntegrations::EventIntegration",
            "AWS::AppMesh::Route",
            "AWS::AppMesh::VirtualRouter",
            "AWS::AppRunner::Service",
            "AWS::Athena::PreparedStatement",
            "AWS::CustomerProfiles::ObjectType",
            "AWS::EC2::CapacityReservation",
            "AWS::EC2::IPAMScope",
            "AWS::Evidently::Launch",
            "AWS::Forecast::DatasetGroup",
            "AWS::GreengrassV2::ComponentVersion",
            "AWS::GroundStation::MissionProfile",
            "AWS::Kendra::Index",
            "AWS::KinesisVideo::Stream",
            "AWS::Logs::Destination",
            "AWS::MSK::Configuration",
            "AWS::MediaConnect::FlowEntitlement",
            "AWS::MediaConnect::FlowVpcInterface",
            "AWS::MediaTailor::PlaybackConfiguration",
            "AWS::NetworkManager::CustomerGatewayAssociation",
            "AWS::NetworkManager::LinkAssociation",
            "AWS::Personalize::Dataset",
            "AWS::Personalize::Schema",
            "AWS::Personalize::Solution",
            "AWS::Pinpoint::EmailChannel",
            "AWS::Pinpoint::EmailTemplate",
            "AWS::Pinpoint::EventStream",
            "AWS::ResilienceHub::App",
            # q2 2023 wave 3
            "AWS::Amplify::App",
            "AWS::AppMesh::VirtualService",
            "AWS::AppRunner::VpcConnector",
            "AWS::AppStream::Application",
            "AWS::Cassandra::Keyspace",
            "AWS::ECS::TaskSet",
            "AWS::Evidently::Project",
            "AWS::Forecast::Dataset",
            "AWS::Pinpoint::Campaign",
            "AWS::Pinpoint::InAppTemplate",
            "AWS::SageMaker::Domain",
            "AWS::Signer::SigningProfile",
            "AWS::Transfer::Agreement",
            "AWS::Transfer::Connector",
            # q2 2023 wave 2
            "AWS::AppConfig::DeploymentStrategy",
            "AWS::AuditManager::Assessment",
            "AWS::CloudWatch::MetricStream",
            "AWS::DeviceFarm::InstanceProfile",
            "AWS::EC2::EC2Fleet",
            "AWS::EC2::SubnetRouteTableAssociation",
            "AWS::ECR::PullThroughCacheRule",
            "AWS::GroundStation::Config",
            "AWS::ImageBuilder::ImagePipeline",
            "AWS::IoT::FleetMetric",
            "AWS::IoTWireless::ServiceProfile",
            "AWS::Panorama::Package",
            "AWS::Pinpoint::App",
            "AWS::Redshift::ScheduledAction",
            "AWS::Route53Resolver::FirewallRuleGroupAssociation",
            "AWS::SageMaker::AppImageConfig",
            "AWS::SageMaker::Image",
            # q2 2023 wave 1
            "AWS::AppStream::DirectoryConfig",
            "AWS::AutoScaling::WarmPool",
            "AWS::Connect::PhoneNumber",
            "AWS::CustomerProfiles::Domain",
            "AWS::EC2::DHCPOptions",
            "AWS::EC2::IPAM",
            "AWS::EC2::NetworkInsightsPath",
            "AWS::EC2::TrafficMirrorFilter",
            "AWS::HealthLake::FHIRDatastore",
            "AWS::IoTTwinMaker::Scene",
            "AWS::KinesisVideo::SignalingChannel",
            "AWS::LookoutVision::Project",
            "AWS::NetworkManager::TransitGatewayRegistration",
            "AWS::Pinpoint::ApplicationSettings",
            "AWS::Pinpoint::Segment",
            "AWS::RoboMaker::RobotApplication",
            "AWS::RoboMaker::SimulationApplication",
            "AWS::Route53RecoveryReadiness::ResourceSet",
            "AWS::Route53RecoveryControl::RoutingControl",
            "AWS::Route53RecoveryControl::SafetyRule",
            # q1 2023
            'AWS::AppConfig::ConfigurationProfile',
            'AWS::AppConfig::Environment',
            'AWS::Backup::ReportPlan',
            'AWS::Budgets::BudgetsAction',
            'AWS::Cloud9::EnvironmentEC2',
            'AWS::CodeGuruReviewer::RepositoryAssociation',
            'AWS::DataSync::LocationFSxWindows',
            'AWS::DataSync::LocationHDFS',
            'AWS::DataSync::LocationObjectStorage',
            'AWS::DeviceFarm::TestGridProject',
            'AWS::ECR::RegistryPolicy',
            'AWS::EKS::Addon',
            'AWS::EKS::IdentityProviderConfig',
            'AWS::EventSchemas::Discoverer',
            'AWS::EventSchemas::Registry',
            'AWS::EventSchemas::RegistryPolicy',
            'AWS::EventSchemas::Schema',
            'AWS::Events::ApiDestination',
            'AWS::Events::Archive',
            'AWS::Events::Connection',
            'AWS::Events::Endpoint',
            'AWS::FraudDetector::EntityType',
            'AWS::FraudDetector::Label',
            'AWS::FraudDetector::Outcome',
            'AWS::FraudDetector::Variable',
            'AWS::GuardDuty::Filter',
            'AWS::IVS::Channel',
            'AWS::IVS::PlaybackKeyPair',
            'AWS::IVS::RecordingConfiguration',
            'AWS::ImageBuilder::ContainerRecipe',
            'AWS::ImageBuilder::DistributionConfiguration',
            'AWS::ImageBuilder::InfrastructureConfiguration',
            'AWS::IoT::AccountAuditConfiguration',
            'AWS::IoT::Authorizer',
            'AWS::IoT::CustomMetric',
            'AWS::IoT::Dimension',
            'AWS::IoT::MitigationAction',
            'AWS::IoT::Policy',
            'AWS::IoT::RoleAlias',
            'AWS::IoT::ScheduledAudit',
            'AWS::IoT::SecurityProfile',
            'AWS::IoTAnalytics::Channel',
            'AWS::IoTAnalytics::Dataset',
            'AWS::IoTAnalytics::Datastore',
            'AWS::IoTAnalytics::Pipeline',
            'AWS::IoTEvents::AlarmModel',
            'AWS::IoTEvents::DetectorModel',
            'AWS::IoTEvents::Input',
            'AWS::IoTSiteWise::AssetModel',
            'AWS::IoTSiteWise::Dashboard',
            'AWS::IoTSiteWise::Gateway',
            'AWS::IoTSiteWise::Portal',
            'AWS::IoTSiteWise::Project',
            'AWS::IoTTwinMaker::Entity',
            'AWS::IoTTwinMaker::Workspace',
            'AWS::Lex::BotAlias',
            'AWS::Lightsail::Bucket',
            'AWS::Lightsail::Certificate',
            'AWS::Lightsail::Disk',
            'AWS::Lightsail::StaticIp',
            'AWS::LookoutMetrics::Alert',
            'AWS::MediaPackage::PackagingConfiguration',
            'AWS::MediaPackage::PackagingGroup',
            'AWS::RDS::GlobalCluster',
            'AWS::RUM::AppMonitor',
            'AWS::ResilienceHub::ResiliencyPolicy',
            'AWS::RoboMaker::RobotApplicationVersion',
            'AWS::Route53RecoveryReadiness::Cell',
            'AWS::Route53RecoveryReadiness::RecoveryGroup',
            'AWS::Route53Resolver::FirewallDomainList',
            'AWS::S3::StorageLens',
            'AWS::SES::ReceiptFilter',
            'AWS::SES::ReceiptRuleSet',
            'AWS::SES::Template',
            'AWS::ServiceDiscovery::HttpNamespace',
            'AWS::Transfer::Workflow',
            #
            # 'AWS::ApiGatewayV2::Stage',
            'AWS::AutoScaling::ScheduledAction',
            'AWS::Backup::BackupSelection',
            'AWS::Backup::RecoveryPoint',
            # 'AWS::CodeDeploy::DeploymentConfig',
            'AWS::Config::ConformancePackCompliance',
            'AWS::Config::ResourceCompliance',
            'AWS::Detective::Graph',
            'AWS::DMS::Certificate',
            'AWS::EC2::EgressOnlyInternetGateway',
            'AWS::EC2::LaunchTemplate',
            'AWS::EC2::RegisteredHAInstance',
            'AWS::EC2::TransitGatewayAttachment',
            'AWS::EC2::TransitGatewayRouteTable',
            'AWS::ECR::PublicRepository',
            'AWS::EFS::AccessPoint',
            'AWS::EMR::SecurityConfiguration',
            'AWS::ElasticBeanstalk::ApplicationVersion',
            'AWS::GlobalAccelerator::Accelerator',
            'AWS::GlobalAccelerator::Listener',
            'AWS::GlobalAccelerator::EndpointGroup',
            'AWS::GuardDuty::Detector',
            'AWS::Kinesis::StreamConsumer',
            'AWS::NetworkFirewall::FirewallPolicy',
            'AWS::NetworkFirewall::RuleGroup',
            'AWS::OpenSearch::Domain',  # this is effectively an alias
            'AWS::RDS::DBSecurityGroup',
            'AWS::RDS::EventSubscription',
            'AWS::Redshift::ClusterParameterGroup',
            'AWS::Redshift::ClusterSecurityGroup',
            'AWS::Redshift::EventSubscription',
            'AWS::S3::AccountPublicAccessBlock',
            'AWS::SSM::AssociationCompliance',
            'AWS::SSM::FileData',
            'AWS::SSM::ManagedInstanceInventory',
            'AWS::SSM::PatchCompliance',
            'AWS::SageMaker::CodeRepository',
            'AWS::ServiceCatalog::CloudFormationProvisionedProduct',
            'AWS::ShieldRegional::Protection',
            'AWS::WAF::RateBasedRule',
            'AWS::WAF::Rule',
            'AWS::WAF::RuleGroup',
            'AWS::WAFRegional::RateBasedRule',
            'AWS::WAFRegional::Rule',
            'AWS::WAFRegional::RuleGroup',
            'AWS::WAFv2::IPSet',
            'AWS::WAFv2::ManagedRuleSet',
            'AWS::WAFv2::RegexPatternSet',
            'AWS::WAFv2::RuleGroup',
            # 'AWS::WAFv2::WebACL',
            'AWS::XRay::EncryptionConfig',
            'AWS::ElasticLoadBalancingV2::Listener',
            'AWS::AccessAnalyzer::Analyzer',
            'AWS::WorkSpaces::ConnectionAlias',
            'AWS::DMS::ReplicationSubnetGroup',
            'AWS::Route53Resolver::ResolverEndpoint',
            'AWS::Route53Resolver::ResolverRule',
            'AWS::Route53Resolver::ResolverRuleAssociation',
            'AWS::DMS::EventSubscription',
            'AWS::GlobalAccelerator::Accelerator',
            'AWS::EC2::TransitGatewayAttachment',
            'AWS::GlobalAccelerator::EndpointGroup',
            'AWS::GlobalAccelerator::Listener',
            'AWS::DMS::Certificate',
            'AWS::Detective::Graph',
            'AWS::EC2::TransitGatewayRouteTable',
            'AWS::Glue::Job',
            'AWS::SageMaker::NotebookInstanceLifecycleConfig',
            'AWS::SES::ContactList',
            'AWS::SageMaker::Workteam',
            'AWS::EKS::FargateProfile',
            'AWS::DataSync::LocationFSxLustre',
            'AWS::AppConfig::Application',
            'AWS::DataSync::LocationS3',
            'AWS::ServiceDiscovery::PublicDnsNamespace',
            'AWS::EC2::NetworkInsightsAccessScopeAnalysis',
            'AWS::Route53::HostedZone',
            'AWS::GuardDuty::IPSet',
            'AWS::GuardDuty::ThreatIntelSet',
            'AWS::DataSync::LocationNFS',
            'AWS::DataSync::LocationEFS',
            'AWS::ServiceDiscovery::Service',
            'AWS::DataSync::LocationSMB',
        }

        resource_map = {}
        for k, v in manager.resources.items():
            if not v.resource_type.config_type:
                continue
            resource_map[v.resource_type.config_type] = v
        resource_config_types = set(resource_map)

        session = fake_session()._session
        model = session.get_service_model('config')
        shape = model.shape_for('ResourceType')

        present = resource_config_types.intersection(whitelist)
        if present:
            raise AssertionError(
                "Supported config types \n %s" % ('\n'.join(sorted(present))))

        config_types = set(shape.enum).difference(whitelist)
        missing = config_types.difference(resource_config_types)
        if missing:
            raise AssertionError(
                "Missing config types \n %s" % ('\n'.join(sorted(missing))))

        # config service can't be bothered to update their sdk correctly
        invalid_ignore = {
            'AWS::Config::ConfigurationRecorder',
            'AWS::SageMaker::NotebookInstance',
            'AWS::SageMaker::EndpointConfig',
            'AWS::DMS::ReplicationInstance',
            'AWS::DMS::ReplicationTask',
            'AWS::SES::MailManagerIngressPoint',
        }
        bad_types = resource_config_types.difference(config_types)
        bad_types = bad_types.difference(invalid_ignore)
        if bad_types:
            raise AssertionError(
                "Invalid config types \n %s" % ('\n'.join(bad_types)))

    def test_resource_meta_with_class(self):
        missing = set()
        for k, v in manager.resources.items():
            if k in ('rest-account', 'account', 'quicksight-account'):
                continue
            if not issubclass(v.resource_type, TypeInfo):
                missing.add(k)
        if missing:
            raise SyntaxError("missing type info class %s" % (', '.join(missing)))

    def test_resource_type_empty_metadata(self):
        empty = set()
        for k, v in manager.resources.items():
            if k in ('rest-account', 'account', 'codedeploy-deployment', 'sagemaker-cluster',
                     'networkmanager-core', 'quicksight-account', 'ses-dedicated-ip-pool'):
                continue
            for rk, rv in v.resource_type.__dict__.items():
                if rk[0].isalnum() and rv is None:
                    empty.add(k)
        if empty:
            raise ValueError("Empty Resource Metadata %s" % (', '.join(empty)))

    def test_valid_arn_type(self):
        arn_db = load_data('arn-types.json')
        invalid = {}
        overrides = {'wafv2': set(('webacl',))}

        # we have a few resources where we have synthetic arns
        # or they aren't in the iam ref docs.
        allow_list = set((
            # bug in the arnref script or test logic below.
            'glue-catalog',
            # these are valid, but v1 & v2 arns get mangled into the
            # same top level prefix
            'emr-serverless-app',
            # api gateway resources trip up these checks because they
            # have leading slashes in the resource type section
            'rest-api',
            'rest-stage',
            'apigw-domain-name',
            # our check doesn't handle nested resource types in the arn
            'guardduty-finding',
            # synthetics ~ ie. c7n introduced since non exist.
            # or in some cases where it exists but not usable in iam.
            'scaling-policy',
            'glue-classifier',
            'glue-security-configuration',
            'event-rule-target',
            'rrset',
            'redshift-reserved',
            'elasticsearch-reserved',
            'ses-receipt-rule-set',
        ))

        for k, v in manager.resources.items():
            if k in allow_list:
                continue
            svc = v.resource_type.service
            if not v.resource_type.arn_type:
                continue

            svc_arn_map = arn_db.get(svc, {})
            if not svc_arn_map:
                continue

            svc_arns = list(svc_arn_map.values())
            svc_arn_types = set()
            for sa in svc_arns:
                sa_arn = Arn.parse(sa)
                sa_type = sa_arn.resource_type
                if sa_type is None:
                    sa_type = ''
                # wafv2
                if sa_type.startswith('{') and sa_type.endswith('}'):
                    sa_type = sa_arn.resource
                if ':' in sa_type:
                    sa_type = sa_type.split(':', 1)[0]
                svc_arn_types.add(sa_type)

            svc_arn_types = overrides.get(svc, svc_arn_types)
            if v.resource_type.arn_type not in svc_arn_types:
                invalid[k] = {'valid': sorted(svc_arn_types),
                              'service': svc,
                              'resource': v.resource_type.arn_type}

        # s3 directory has bucket in the arn, but its not in the iam ref docs
        # we source arn types from.
        for ignore in ('s3-directory',):
            invalid.pop(ignore)

        if invalid:
            raise ValueError("%d %s have invalid arn types in metadata" % (
                len(invalid), ", ".join(invalid)))

    def test_resource_legacy_type(self):
        legacy = set()
        marker = object()
        for k, v in manager.resources.items():
            if getattr(v.resource_type, 'type', marker) is not marker:
                legacy.add(k)
        if legacy:
            raise SyntaxError("legacy arn type info %s" % (', '.join(legacy)))

    def _visit_filters_and_actions(self, visitor):
        names = []
        for cloud_name, cloud in clouds.items():
            for resource_name, resource in cloud.resources.items():
                for fname, f in resource.filter_registry.items():
                    if fname in ('and', 'or', 'not'):
                        continue
                    if visitor(f):
                        names.append("%s.%s.filters.%s" % (
                            cloud_name, resource_name, fname))
                for aname, a in resource.action_registry.items():
                    if visitor(a):
                        names.append('%s.%s.actions.%s' % (
                            cloud_name, resource_name, aname))
        return names

    def test_filter_action_additional(self):

        def visitor(e):
            if e.type == 'notify':
                return
            return e.schema.get('additionalProperties', True) is True

        names = self._visit_filters_and_actions(visitor)
        if names:
            self.fail(
                "missing additionalProperties: False on actions/filters\n %s" % (
                    " \n".join(names)))

    def test_filter_action_type(self):
        def visitor(e):
            return 'type' not in e.schema['properties']

        names = self._visit_filters_and_actions(visitor)
        if names:
            self.fail("missing type on actions/filters\n %s" % (" \n".join(names)))

    def test_resource_arn_info(self):
        missing = []
        whitelist_missing = {
            'rest-stage', 'rest-resource', 'rest-vpclink', 'rest-client-certificate'}
        explicit = []
        whitelist_explicit = {
            'securityhub-finding', 'ssm-patch-group',
            'appdiscovery-agent', 'athena-named-query',
            'rest-account', 'shield-protection', 'shield-attack',
            'dlm-policy', 'efs', 'efs-mount-target', 'gamelift-build',
            'glue-connection', 'glue-dev-endpoint', 'cloudhsm-cluster',
            'snowball-cluster', 'snowball', 'ssm-activation',
            'healthcheck', 'event-rule-target', 'log-metric',
            'support-case', 'transit-attachment', 'config-recorder',
            'apigw-domain-name', 'backup-job', 'quicksight-account', 'codedeploy-config'}

        missing_method = []
        for k, v in manager.resources.items():
            rtype = getattr(v, 'resource_type', None)
            if not v.has_arn():
                missing_method.append(k)
            if rtype is None:
                continue
            if v.__dict__.get('get_arns'):
                continue
            if getattr(rtype, 'arn', None) is False:
                explicit.append(k)
            if getattr(rtype, 'arn', None) is not None:
                continue
            if getattr(rtype, 'type', None) is not None:
                continue
            if getattr(rtype, 'arn_type', None) is not None:
                continue
            missing.append(k)

        self.assertEqual(
            set(missing).union(explicit),
            set(missing_method))

        missing = set(missing).difference(whitelist_missing)
        if missing:
            self.fail(
                "%d resources %s are missing arn type info" % (
                    len(missing), ", ".join(missing)))
        explicit = set(explicit).difference(whitelist_explicit)
        if explicit:
            self.fail(
                "%d resources %s dont have arn type info exempted" % (
                    len(explicit), ", ".join(explicit)))

    def test_resource_permissions(self):

        ignore_elements = set((
            # this service has been fully removed, we're keeping compatiblity
            # support for the moment to avoid breaking policies targeting.
            #
            "opswork-cm",
            "opswork-cm.actions.delete",
            "opswork-stack",
            "opswork-stack.actions.delete",
            "opswork-stack.actions.stop",
            "route-table.filters.route",
        ))

        self.capture_logging("c7n.cache")
        missing = []
        cfg = Config.empty()

        for k, v in list(manager.resources.items()):
            p = Bag({"name": "permcheck", "resource": k, 'provider_name': 'aws'})
            ctx = self.get_context(config=cfg, policy=p)
            mgr = v(ctx, p)
            perms = mgr.get_permissions()
            if not perms:
                if k not in ignore_elements:
                    missing.append(k)

            for n, a in list(v.action_registry.items()):
                p["actions"] = [n]
                perms = a({}, mgr).get_permissions()
                found = bool(perms)
                if not isinstance(perms, (list, tuple, set)):
                    found = False
                if "webhook" == n:
                    continue
                if not found:
                    qk = "%s.actions.%s" % (k, n)
                    if qk not in ignore_elements:
                        missing.append(qk)

            for n, f in list(v.filter_registry.items()):
                if n in ("and", "or", "not", "missing", "reduce"):
                    continue
                p["filters"] = [n]
                perms = f({}, mgr).get_permissions()
                if not isinstance(perms, (tuple, list, set)):
                    missing.append("%s.filters.%s" % (k, n))

                # in memory filters
                if n in (
                    "event",
                    "value",
                    "tag-count",
                    "marked-for-op",
                    "offhour",
                    "onhour",
                    "age",
                    "state-age",
                    "egress",
                    "ingress",
                    "capacity-delta",
                    "is-ssl",
                    "global-grants",
                    "missing-policy-statement",
                    "missing-statement",
                    "healthcheck-protocol-mismatch",
                    "image-age",
                    "has-statement",
                    "no-access",
                    "instance-age",
                    "ephemeral",
                    "instance-uptime",
                    "dead-letter",
                    "list-item",
                    "ip-address-usage",
                ):
                    continue
                qk = "%s.filters.%s" % (k, n)
                if qk in ignore_elements:
                    continue
                if not perms:
                    missing.append(qk)

        if missing:
            self.fail(
                "Missing permissions %d on \n\t%s"
                % (len(missing), "\n\t".join(sorted(missing)))
            )

    def test_deprecation_dates(self):
        def check_deprecations(source):
            issues = set()
            for dep in getattr(source, 'deprecations', ()):
                when = dep.removed_after
                if when is not None:
                    name = f"{source.__module__}.{source.__name__}"
                    if not isinstance(when, str):
                        issues.add(f"{name}: \"{dep}\", removed_after attribute must be a string")
                        continue
                    try:
                        datetime.strptime(when, "%Y-%m-%d")
                    except ValueError:
                        issues.add(f"{name}: \"{dep}\", removed_after must be a valid date"
                                   f" in the format 'YYYY-MM-DD', got '{when}'")
            return issues
        issues = check_deprecations(Policy)
        for name, cloud in clouds.items():
            for resource_name, resource in cloud.resources.items():
                issues = issues.union(check_deprecations(resource))
                for fname, f in resource.filter_registry.items():
                    if fname in ('and', 'or', 'not'):
                        continue
                    issues = issues.union(check_deprecations(f))
                for aname, a in resource.action_registry.items():
                    issues = issues.union(check_deprecations(a))
        for name, mode in execution.items():
            issues = issues.union(check_deprecations(mode))
        if issues:
            self.fail(
                "Deprecation validation issues with \n\t%s" %
                "\n\t".join(sorted(issues))
            )


class PolicyMeta(BaseTest):

    def test_policy_detail_spec_permissions(self):
        policy = self.load_policy(
            {"name": "kinesis-delete",
             "resource": "kinesis",
             "actions": ["delete"]}
        )
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            {
                "kinesis:DescribeStream",
                "kinesis:ListStreams",
                "kinesis:DeleteStream",
                "kinesis:ListTagsForStream",
                "tag:GetResources"
            },
        )

    def test_policy_manager_custom_permissions(self):
        policy = self.load_policy(
            {
                "name": "ec2-utilization",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "CPUUtilization",
                        "days": 3,
                        "value": 1.5,
                    }
                ],
            }
        )
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            {
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "cloudwatch:GetMetricStatistics",
            },
        )


class TestPolicyCollection(BaseTest):

    def test_expand_partitions(self):
        cfg = Config.empty(regions=["us-gov-west-1", "cn-north-1", "us-west-2"])
        original = policy.PolicyCollection.from_data(
            {"policies": [{"name": "foo", "resource": "ec2"}]}, cfg
        )

        collection = AWS().initialize_policies(original, cfg)
        self.assertEqual(
            sorted([p.options.region for p in collection]),
            ["cn-north-1", "us-gov-west-1", "us-west-2"],
        )

    def test_policy_expand_group_region(self):
        cfg = Config.empty(regions=["us-east-1", "us-east-2", "us-west-2"])
        original = policy.PolicyCollection.from_data(
            {"policies": [
                {"name": "bar", "resource": "lambda"},
                {"name": "middle", "resource": "security-group"},
                {"name": "foo", "resource": "ec2"}]},
            cfg)

        collection = AWS().initialize_policies(original, cfg)
        self.assertEqual(
            [(p.name, p.options.region) for p in collection],
            [('bar', 'us-east-1'),
             ('middle', 'us-east-1'),
             ('foo', 'us-east-1'),
             ('bar', 'us-east-2'),
             ('middle', 'us-east-2'),
             ('foo', 'us-east-2'),
             ('bar', 'us-west-2'),
             ('middle', 'us-west-2'),
             ('foo', 'us-west-2')])

    def test_policy_region_expand_global(self):
        factory = self.replay_flight_data('test_aws_policy_global_expand')
        self.patch(aws, '_profile_session', factory())
        original = self.policy_loader.load_data(
            {"policies": [
                {"name": "foo", "resource": "s3"},
                {"name": "iam", "resource": "iam-user"}]},
            'memory://',
            config=Config.empty(regions=["us-east-1", "us-west-2"]),
        )

        collection = AWS().initialize_policies(
            original, Config.empty(regions=["all"], output_dir="/test/output/"))
        self.assertEqual(len(collection.resource_types), 2)
        s3_regions = [p.options.region for p in collection if p.resource_type == "s3"]
        self.assertTrue("us-east-1" in s3_regions)
        self.assertTrue("us-east-2" in s3_regions)
        iam = [p for p in collection if p.resource_type == "iam-user"]
        self.assertEqual(len(iam), 1)
        self.assertEqual(iam[0].options.region, "us-east-1")
        self.assertEqual(iam[0].options.output_dir, "/test/output/us-east-1")

        # Don't append region when it's already in the path.
        collection = AWS().initialize_policies(
            original, Config.empty(regions=["all"], output_dir="/test/{region}/output/"))
        self.assertEqual(len(collection.resource_types), 2)
        iam = [p for p in collection if p.resource_type == "iam-user"]
        self.assertEqual(iam[0].options.region, "us-east-1")
        self.assertEqual(iam[0].options.output_dir, "/test/{region}/output")

        collection = AWS().initialize_policies(
            original, Config.empty(regions=["eu-west-1", "eu-west-2"], output_dir="/test/output/")
        )
        iam = [p for p in collection if p.resource_type == "iam-user"]
        self.assertEqual(len(iam), 1)
        self.assertEqual(iam[0].options.region, "eu-west-1")
        self.assertEqual(iam[0].options.output_dir, "/test/output/eu-west-1")
        self.assertEqual(len(collection), 3)

    def test_policy_filter_mode(self):
        cfg = Config.empty(regions=['us-east-1'])
        original = policy.PolicyCollection.from_data(
            {"policies": [
                {
                    "name": "bar",
                    "resource": "lambda",
                    "mode": {
                        "type": "cloudtrail",
                        "events": ["CreateFunction"],
                        "role": "custodian"
                    }
                },
                {
                    "name": "two",
                    "resource": "ec2",
                    "mode": {
                        "type": "periodic",
                        "role": "cutodian",
                        "schedule": "rate(1 day)"
                    }
                }
            ]}, cfg)
        collection = AWS().initialize_policies(original, cfg)
        result = collection.filter(modes=['cloudtrail'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.policies[0].name, 'bar')


class TestPolicy(BaseTest):

    def test_policy_variable_precedent(self):
        p = self.load_policy({
            'name': 'compute',
            'resource': 'aws.ec2'},
            config={'account_id': '00100100'})

        v = p.get_variables({'account_id': 'foobar',
                             'charge_code': 'oink'})
        self.assertEqual(v['account_id'], '00100100')
        self.assertEqual(v['charge_code'], 'oink')

    def test_policy_with_role_complete(self):
        p = self.load_policy({
            'name': 'compute',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'config-rule',
                'member-role': 'arn:aws:iam::{account_id}:role/BarFoo',
                'role': 'arn:aws:iam::{account_id}:role/FooBar'},
            'actions': [
                {'type': 'tag',
                 'value': 'bad monkey {account_id} {region} {now:+2d%Y-%m-%d}'},
                {'type': 'notify',
                 'to': ['me@example.com'],
                 'transport': {
                     'type': 'sns',
                     'topic': 'arn:::::',
                 },
                 'subject': "S3 - Cross-Account -[custodian {{ account }} - {{ region }}]"},
            ]}, config={'account_id': '12312311', 'region': 'zanzibar'})

        assert p.get_execution_mode().get_permissions() == ()
        p.expand_variables(p.get_variables())
        self.assertEqual(p.data['mode']['role'], 'arn:aws:iam::12312311:role/FooBar')

    def test_policy_variable_interpolation(self):

        p = self.load_policy({
            'name': 'compute',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'config-rule',
                'member-role': 'arn:aws:iam::{account_id}:role/BarFoo',
                'role': 'FooBar'},
            'actions': [
                {'type': 'notify',
                 'to': ['me@example.com'],
                 'transport': {
                     'type': 'sns',
                     'topic': 'arn:::::',
                 },
                 'subject': "S3 - Cross-Account -[custodian {{ account }} - {{ region }}]"},
            ]}, config={'account_id': '12312311', 'region': 'zanzibar'})

        p.expand_variables(p.get_variables())
        self.assertEqual(
            p.data['actions'][0]['subject'],
            "S3 - Cross-Account -[custodian {{ account }} - {{ region }}]")
        self.assertEqual(p.data['mode']['role'], 'arn:aws:iam::12312311:role/FooBar')
        self.assertEqual(p.data['mode']['member-role'], 'arn:aws:iam::{account_id}:role/BarFoo')

    def test_now_interpolation(self):
        """Test interpolation of the {now} placeholder

        - Only interpolate the value at runtime, not during provisioning
        - When deferring interpolation, pass through custom format specifiers
        """

        pull_mode_policy = self.load_policy({
            'name': 'compute',
            'resource': 'aws.ec2',
            'actions': [
                {'type': 'tag',
                 'value': 'bad monkey {account_id} {region} {now:+2d%Y-%m-%d}'},
                {'type': 'tag',
                 'key': 'escaped_braces',
                 'value': '{{now}}'},
            ]}, config={'account_id': '12312311', 'region': 'zanzibar'})
        lambda_mode_policy = self.load_policy({
            **pull_mode_policy.data,
            **{
                'mode': {
                    'type': 'config-rule',
                    'role': 'FooBar'},
            }
        }, config=pull_mode_policy.ctx.options)

        provision_time_value = 'bad monkey 12312311 zanzibar {now:+2d%Y-%m-%d}'
        run_time_value = 'bad monkey 12312311 zanzibar %s' % (
            (datetime.utcnow() + timedelta(2)).strftime('%Y-%m-%d'))

        pull_mode_policy.expand_variables(pull_mode_policy.get_variables())
        self.assertEqual(
            pull_mode_policy.data['actions'][0]['value'],
            run_time_value
        )
        self.assertEqual(
            pull_mode_policy.resource_manager.actions[0].data['value'],
            run_time_value
        )

        lambda_mode_policy.expand_variables(lambda_mode_policy.get_variables())
        self.assertEqual(
            lambda_mode_policy.data['actions'][0]['value'],
            provision_time_value
        )
        self.assertEqual(
            lambda_mode_policy.resource_manager.actions[0].data['value'],
            provision_time_value
        )
        # Validate historical use of {{now}} to defer interpolation
        self.assertEqual(
            lambda_mode_policy.resource_manager.actions[1].data['value'],
            '{now}'
        )

    def test_child_resource_trail_validation(self):
        self.assertRaises(
            ValueError,
            self.load_policy,
            {
                "name": "api-resources",
                "resource": "rest-resource",
                "mode": {
                    "type": "cloudtrail",
                    "events": [
                        {
                            "source": "apigateway.amazonaws.com",
                            "event": "UpdateResource",
                            "ids": "requestParameter.stageName",
                        }
                    ],
                },
            },
        )

    def test_load_policy_validation_error(self):
        invalid_policies = {
            "policies": [
                {
                    "name": "foo",
                    "resource": "s3",
                    "filters": [{"tag:custodian_tagging": "not-null"}],
                    "actions": [
                        {"type": "untag", "tags": {"custodian_cleanup": "yes"}}
                    ],
                }
            ]
        }
        self.assertRaises(Exception, self.load_policy_set, invalid_policies)

    def test_policy_validation(self):
        policy = self.load_policy(
            {
                "name": "ec2-utilization",
                "resource": "ec2",
                "tags": ["abc"],
                "filters": [
                    {
                        "type": "metrics",
                        "name": "CPUUtilization",
                        "days": 3,
                        "value": 1.5,
                    }
                ],
                "actions": ["stop"],
            }
        )
        policy.validate()
        self.assertEqual(policy.tags, ["abc"])
        self.assertFalse(policy.is_lambda)
        self.assertTrue(
            repr(policy).startswith("<Policy resource:ec2 name:ec2-utilization")
        )

    def test_policy_name_and_resource_type_filtering(self):

        collection = self.load_policy_set(
            {
                "policies": [
                    {"name": "s3-remediate", "resource": "s3"},
                    {"name": "s3-global-grants", "resource": "s3"},
                    {"name": "ec2-tag-compliance-stop", "resource": "ec2"},
                    {"name": "ec2-tag-compliance-kill", "resource": "ec2"},
                    {"name": "ec2-tag-compliance-remove", "resource": "ec2"},
                ]
            }
        )

        self.assertIn("s3-remediate", collection)
        self.assertNotIn("s3-argle-bargle", collection)

        # Make sure __iter__ works
        for p in collection:
            self.assertTrue(p.name is not None)

        self.assertEqual(collection.resource_types, {"s3", "ec2"})
        self.assertTrue("s3-remediate" in collection)

        self.assertEqual(
            [p.name for p in collection.filter(["s3*"])],
            ["s3-remediate", "s3-global-grants"],
        )

        self.assertEqual(
            [p.name for p in collection.filter(["ec2*"])],
            [
                "ec2-tag-compliance-stop",
                "ec2-tag-compliance-kill",
                "ec2-tag-compliance-remove",
            ],
        )

        self.assertEqual(
            [p.name for p in collection.filter(["ec2*", "s3*"])],
            [p.name for p in collection],
        )

        self.assertEqual(
            [p.name for p in collection.filter(resource_types=["ec2"])],
            [
                "ec2-tag-compliance-stop",
                "ec2-tag-compliance-kill",
                "ec2-tag-compliance-remove",
            ],
        )

        self.assertEqual(
            [p.name for p in collection.filter(resource_types=["ec2", "s3"])],
            [p.name for p in collection],
        )

        self.assertEqual(
            [p.name for p in collection.filter(["ec2*", "s3*"], ["ec2", "s3"])],
            [p.name for p in collection],
        )

        self.assertEqual(
            [p.name for p in collection.filter(["ec2*", "s3*"], ["s3"])],
            [
                "s3-remediate",
                "s3-global-grants",
            ],
        )

        self.assertEqual(
            [p.name for p in collection.filter(["asdf12"])],
            [],
        )

        self.assertEqual(
            [p.name for p in collection.filter(resource_types=["asdf12"])],
            [],
        )

    def test_file_not_found(self):
        self.assertRaises(IOError, policy.load, Config.empty(), "/asdf12")

    def test_policy_resource_limits(self):
        session_factory = self.replay_flight_data(
            "test_policy_resource_limits")
        p = self.load_policy(
            {
                "name": "log-delete",
                "resource": "log-group",
                "max-resources-percent": 2.5,
            },
            session_factory=session_factory)
        p.ctx.metrics.flush = mock.MagicMock()
        output = self.capture_logging('custodian.policy', level=logging.ERROR)
        self.assertRaises(ResourceLimitExceeded, p.run)
        self.assertEqual(
            output.getvalue().strip(),
            "policy:log-delete exceeded resource-limit:2.5% found:1 total:1")
        self.assertEqual(
            p.ctx.metrics.buf[0]['MetricName'], 'ResourceLimitExceeded')

    def test_policy_resource_limits_count(self):
        session_factory = self.replay_flight_data(
            "test_policy_resource_count")
        p = self.load_policy(
            {
                "name": "ecs-cluster-resource-count",
                "resource": "ecs",
                "max-resources": 1
            },
            session_factory=session_factory)
        self.assertRaises(ResourceLimitExceeded, p.run)
        policy = {
            "name": "ecs-cluster-resource-count",
            "resource": "ecs",
            "max-resources": 0
        }
        config = Config.empty(validate=True)
        self.assertRaises(
            Exception,
            self.load_policy,
            policy,
            config=config,
            validate=True,
            session_factory=session_factory
        )

    def test_policy_resource_limit_and_percent(self):
        session_factory = self.replay_flight_data(
            "test_policy_resource_count")
        p = self.load_policy(
            {
                "name": "ecs-cluster-resource-count",
                "resource": "ecs",
                "max-resources": {
                    "amount": 1,
                    "percent": 10,
                    "op": "and"
                }
            },
            session_factory=session_factory)
        self.assertRaises(ResourceLimitExceeded, p.run)
        p = self.load_policy(
            {
                "name": "ecs-cluster-resource-count",
                "resource": "ecs",
                "max-resources": {
                    "amount": 100,
                    "percent": 10,
                    "op": "and"
                }
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertTrue(resources)

    def test_policy_resource_limits_with_filter(self):
        session_factory = self.replay_flight_data(
            "test_policy_resource_count_with_filter")
        p = self.load_policy(
            {
                "name": "asg-with-image-age-resource-count",
                "resource": "asg",
                "max-resources": 1,
                "filters": [{
                    "type": "image-age",
                    "op": "ge",
                    "days": 0
                }]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertTrue(resources)

    def test_get_resource_manager(self):
        collection = self.load_policy_set(
            {
                "policies": [
                    {
                        "name": "query-instances",
                        "resource": "ec2",
                        "filters": [{"tag-key": "CMDBEnvironment"}],
                    }
                ]
            }
        )
        p = collection.policies[0]
        self.assertTrue(isinstance(p.load_resource_manager(), EC2))

    def xtest_policy_run(self):
        manager.resources.register("dummy", DummyResource)
        self.addCleanup(manager.resources.unregister, "dummy")
        self.output_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.output_dir)

        collection = self.load_policy_set(
            {"policies": [{"name": "process-instances", "resource": "dummy"}]},
            {"output_dir": self.output_dir},
        )
        p = collection.policies[0]
        p()
        self.assertEqual(len(p.ctx.metrics.data), 3)

    def test_validate_policy_start_stop(self):
        data = {
            'name': 'bad-str-parse',
            'resource': 'ec2',
            'start': 'asdf'
        }
        with self.assertRaises(ValueError):
            self.load_policy(data)

        data = {
            'name': 'bad-non-str-parse',
            'resource': 'ec2',
            'start': 2
        }
        with self.assertRaises(Exception):
            self.load_policy(data)

        data = {
            'name': 'bad-tz-parse',
            'resource': 'ec2',
            'tz': 'asdf'
        }
        with self.assertRaises(PolicyValidationError):
            self.load_policy(data)

        data = {
            'name': 'bad-tz-int-parse',
            'resource': 'ec2',
            'tz': 2
        }
        with self.assertRaises(Exception):
            self.load_policy(data)

        data = {
            'name': 'good-time-parse',
            'resource': 'ec2',
            'start': '4 AM'
        }
        p = self.load_policy(data)
        result = p.validate_policy_start_stop()
        self.assertEqual(result, None)

        data = {
            'name': 'good-tz-str-parse',
            'resource': 'ec2',
            'tz': 'UTC'
        }

        p = self.load_policy(data)
        result = p.validate_policy_start_stop()
        self.assertEqual(result, None)


class PolicyConditionsTest(BaseTest):

    def test_value_from(self):
        tmp_dir = self.change_cwd()
        p = self.load_policy({
            'name': 'fx',
            'resource': 'aws.ec2',
            'conditions': [{
                'type': 'value',
                'key': 'account_id',
                'op': 'in',
                'value_from': {
                    'url': 'file:///{}/accounts.txt'.format(tmp_dir),
                    'type': 'txt'}
            }]
        })
        with open(os.path.join(tmp_dir, 'accounts.txt'), 'w') as fh:
            fh.write(p.ctx.options.account_id)
        self.assertTrue(p.is_runnable())

    def test_env_var_extension(self):
        p = self.load_policy({
            'name': 'profx',
            'resource': 'aws.ec2',
            'conditions': [{
                'type': 'value',
                'key': 'account.name',
                'value': 'deputy'}]})
        p.conditions.env_vars['account'] = {'name': 'deputy'}
        self.assertTrue(p.is_runnable())
        p.conditions.env_vars['account'] = {'name': 'mickey'}
        self.assertFalse(p.is_runnable())

    def test_env_var_extension_with_expand_variables(self):
        p_json = {
            'name': 'profx',
            'resource': 'aws.ec2',
            'description': 'Test var extension {var1}',
            'conditions': [{
                'type': 'value',
                'key': 'account.name',
                'value': 'deputy'}]}

        p = self.load_policy(p_json)
        p.conditions.env_vars['account'] = {'name': 'deputy'}
        p.expand_variables({"var1": "value1"})
        p.validate()
        self.assertEqual("Test var extension value1", p.data["description"])
        self.assertTrue(p.is_runnable())

        p = self.load_policy(p_json)
        p.conditions.env_vars['account'] = {'name': 'mickey'}
        p.expand_variables({"var1": "value2"})
        p.validate()
        self.assertEqual("Test var extension value2", p.data["description"])
        self.assertFalse(p.is_runnable())

    def test_event_filter(self):
        p = self.load_policy({
            'name': 'profx',
            'resource': 'aws.ec2',
            'conditions': [{
                'type': 'event',
                'key': 'detail.userIdentity.userName',
                'value': 'deputy'}]})
        self.assertTrue(
            p.conditions.evaluate(
                {'detail': {'userIdentity': {'userName': 'deputy'}}}))

        # event filters pass if we don't have an event.
        self.assertTrue(p.is_runnable())
        self.assertFalse(p.is_runnable({}))
        self.assertFalse(p.is_runnable(
            {'detail': {'userIdentity': {'userName': 'mike'}}}))

    def test_boolean_or_blocks(self):
        p = self.load_policy({
            'name': 'magenta',
            'resource': 'aws.codebuild',
            'conditions': [{
                'or': [
                    {'region': 'us-east-1'},
                    {'region': 'us-west-2'}]}]})
        self.assertTrue(p.is_runnable())

    def test_boolean_and_blocks(self):
        p = self.load_policy({
            'name': 'magenta',
            'resource': 'aws.codebuild',
            'conditions': [{
                'and': [
                    {'region': 'us-east-1'},
                    {'region': 'us-west-2'}]}]})
        self.assertFalse(p.is_runnable())

    def test_boolean_not_blocks(self):
        p = self.load_policy({
            'name': 'magenta',
            'resource': 'aws.codebuild',
            'conditions': [{
                'not': [
                    {'region': 'us-east-1'}]}]})
        self.assertFalse(p.is_runnable())

    def test_dryrun_event_filter(self):
        pdata = {
            'name': 'manga',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'config-rule',
                'role': 'something'
            },
            'filters': [{
                'not': [
                    {'type': 'event'}
                ]
            }]
        }
        self.patch(PullMode, 'run', lambda self: [True])
        p = self.load_policy(
            deepcopy(pdata), config={'dryrun': True})
        results = p.run()
        self.assertEqual(results, [True])
        self.assertTrue(p.is_runnable())
        self.assertEqual(pdata, p.data)

    def test_boolean_not_event(self):
        # event is bound to execution evaluation, when
        # evaluating conditions for provisioning we
        # strip any event filters.
        pdata = {
            'name': 'manga',
            'resource': 'aws.ec2',
            'conditions': [{
                'or': [
                    {'not': [
                        {'type': 'event'}]}]}]}
        p = self.load_policy(pdata)
        p._trim_runtime_filters()
        self.assertTrue(p.is_runnable())
        self.assertFalse(p.conditions.filters)
        self.assertEqual(p.data, pdata)


class PolicyExecutionModeTest(BaseTest):

    def test_run_unimplemented(self):
        self.assertRaises(NotImplementedError, policy.PolicyExecutionMode({}).run)

    def test_get_logs_unimplemented(self):
        self.assertRaises(
            NotImplementedError, policy.PolicyExecutionMode({}).get_logs, 1, 2
        )


class LambdaModeTest(BaseTest):

    def test_tags_validation(self):
        log_file = self.capture_logging('c7n.policy', level=logging.INFO)
        self.load_policy({
            'name': 'foobar',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'config-rule',
                'tags': {
                    'custodian-mode': 'xyz',
                    'xyz': 'bar'}
            }},
            validate=True)
        lines = log_file.getvalue().strip().split('\n')
        self.assertEqual(
            lines[0],
            ('Custodian reserves policy lambda tags starting with '
             'custodian - policy specifies custodian-mode'))

    def test_tags_injection(self):
        p = self.load_policy({
            'name': 'foobar',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'schedule',
                'schedule': 'rate(1 day)',
                'scheduler-role': 'arn:aws:iam::644160558196:role/custodian-scheduler-mu',
                'tags': {
                    'xyz': 'bar'
                }
            }},
            validate=True)

        from c7n import mu
        policy_lambda = []

        def publish(self, func, alias=None, role=None, s3_uri=None):
            policy_lambda.append(func)

        self.patch(mu.LambdaManager, 'publish', publish)

        p.provision()
        self.assertEqual(
            policy_lambda[0].tags['custodian-info'],
            'mode=schedule:version=%s' % version)
        self.assertEqual(
            policy_lambda[0].tags['custodian-schedule'],
            'name=custodian-foobar:group=default'
        )


class PullModeTest(BaseTest):

    def test_skip_when_region_not_equal(self):
        log_file = self.capture_logging("custodian.policy")

        policy_name = "rds-test-policy"
        p = self.load_policy(
            {
                "name": policy_name,
                "resource": "rds",
                "region": "us-east-1",
                "filters": [{"type": "default-vpc"}],
            },
            config={"region": "us-west-2"},
            session_factory=None,
        )

        p.run()

        lines = log_file.getvalue().strip().split("\n")
        self.assertIn(
            "Skipping policy:{} due to execution conditions".format(
                policy_name
            ),
            lines,
        )

    def test_is_runnable_mismatch_region(self):
        p = self.load_policy(
            {'name': 'region-mismatch',
             'resource': 'ec2',
             'region': 'us-east-1'},
            config={'region': 'us-west-2', 'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), False)

    def test_is_runnable_dates(self):
        p = self.load_policy(
            {'name': 'good-start-date',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': '2018-3-29'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), True)

        tomorrow_date = str(datetime.date(datetime.now()) + timedelta(days=1))
        p = self.load_policy(
            {'name': 'bad-start-date',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': tomorrow_date},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), False)

        p = self.load_policy(
            {'name': 'good-end-date',
             'resource': 'ec2',
             'tz': 'UTC',
             'end': tomorrow_date},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), True)

        p = self.load_policy(
            {'name': 'bad-end-date',
             'resource': 'ec2',
             'tz': 'UTC',
             'end': '2018-3-29'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), False)

        p = self.load_policy(
            {'name': 'bad-start-end-date',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': '2018-3-28',
             'end': '2018-3-29'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), False)

    def test_is_runnable_parse_dates(self):
        p = self.load_policy(
            {'name': 'parse-date-policy',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': 'March 3 2018'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), True)

        p = self.load_policy(
            {'name': 'parse-date-policy',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': 'March 3rd 2018'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), True)

        p = self.load_policy(
            {'name': 'parse-date-policy',
             'resource': 'ec2',
             'tz': 'UTC',
             'start': '28 March 2018'},
            config={'validate': True},
            session_factory=None)
        self.assertEqual(p.is_runnable(), True)


class PhdModeTest(BaseTest):

    def test_validation(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'xyz', 'resource': 'ec2',
             'mode': {'type': 'phd'}})
        self.load_policy(
            {'name': 'abc', 'resource': 'account',
             'mode': {'type': 'phd'}})


class ConfigModeTest(BaseTest):

    def test_config_poll(self):
        factory = self.replay_flight_data('test_config_poll_rule_evaluation')
        cmock = mock.MagicMock()
        requests = []

        def record_requests(Evaluations, ResultToken):
            requests.extend(Evaluations)

        mocked_evaluations = {
            'EvaluationResults': [
                {
                    'EvaluationResultIdentifier': {
                        'EvaluationResultQualifier': {
                            'ConfigRuleName': 'kin-poll',
                            'ResourceType': 'AWS::Kinesis::Stream',
                            'ResourceId': 'dev1'
                        },
                        'OrderingTimestamp': datetime(2015, 1, 1)
                    },
                    'ComplianceType': 'COMPLIANT',
                    'ResultRecordedTime': datetime(2015, 1, 1),
                    'ConfigRuleInvokedTime': datetime(2015, 1, 1),
                    'Annotation': 'The resource is compliant with policy:kin-poll.',
                },
                {
                    'EvaluationResultIdentifier': {
                        'EvaluationResultQualifier': {
                            'ConfigRuleName': 'kin-poll',
                            'ResourceType': 'AWS::Kinesis::Stream',
                            'ResourceId': 'dev2'
                        },
                        'OrderingTimestamp': datetime(2015, 1, 1)
                    },
                    'ComplianceType': 'NON_COMPLIANT',
                    'ResultRecordedTime': datetime(2015, 1, 1),
                    'ConfigRuleInvokedTime': datetime(2015, 1, 1),
                    'Annotation': 'The resource is not compliant with policy:kin-poll.',
                },
                {
                    'EvaluationResultIdentifier': {
                        'EvaluationResultQualifier': {
                            'ConfigRuleName': 'kin-poll',
                            'ResourceType': 'AWS::Kinesis::Stream',
                            'ResourceId': 'dev3'
                        },
                        'OrderingTimestamp': datetime(2015, 1, 1)
                    },
                    'ComplianceType': 'NON_COMPLIANT',
                    'ResultRecordedTime': datetime(2015, 1, 1),
                    'ConfigRuleInvokedTime': datetime(2015, 1, 1),
                    'Annotation': 'The resource is not compliant with policy:kin-poll.',
                },
            ]
        }

        cmock.put_evaluations.side_effect = record_requests
        cmock.put_evaluations.return_value = {}
        cmock.get_paginator.return_value.paginate.return_value.build_full_result.return_value = \
            mocked_evaluations

        self.patch(
            ConfigPollRuleMode, '_get_client', lambda self: cmock)
        self.patch(
            KinesisStream.resource_type, 'config_type', None)

        p = self.load_policy({
            'name': 'kin-poll',
            'resource': 'aws.kinesis',
            'filters': [{'tag:App': 'Dev'}],
            'mode': {
                'type': 'config-poll-rule',
                'schedule': 'Three_Hours'}},
            session_factory=factory,
            validate=False)

        event = event_data('poll-evaluation.json', 'config')
        results = p.push(event, None)
        self.assertEqual(results, ['dev2'])
        self.assertEqual(
            requests,
            [{'Annotation': 'The resource is not compliant with policy:kin-poll.',
              'ComplianceResourceId': 'dev2',
              'ComplianceResourceType': 'AWS::Kinesis::Stream',
              'ComplianceType': 'NON_COMPLIANT',
              'OrderingTimestamp': '2020-05-03T13:55:44.576Z'},
             {'Annotation': 'The resource is compliant with policy:kin-poll.',
              'ComplianceResourceId': 'dev1',
              'ComplianceResourceType': 'AWS::Kinesis::Stream',
              'ComplianceType': 'COMPLIANT',
              'OrderingTimestamp': '2020-05-03T13:55:44.576Z'},
             {'ComplianceResourceType': 'AWS::Kinesis::Stream',
              'ComplianceResourceId': 'dev3',
              'Annotation': 'The rule does not apply.',
              'ComplianceType': 'NOT_APPLICABLE',
              'OrderingTimestamp': '2020-05-03T13:55:44.576Z'}])

    related_resource_policy = {
        "name": "vpc-flow-logs",
        "resource": "aws.vpc",
        "filters": [
            {
                "type": "flow-logs",
                "destination-type": "s3",
                "enabled": True,
                "status": "active",
            }
        ]
    }

    def test_config_poll_supported_resource_warning(self):
        with self.assertRaisesRegex(
            PolicyValidationError,
            r'fully supported by config'
        ):
            self.load_policy({
                **self.related_resource_policy,
                "mode": {
                    "type": "config-poll-rule",
                    "role": "arn:aws:iam::{account_id}:role/MyRole",
                    "schedule": "TwentyFour_Hours"
                }
            })

    def test_config_poll_ignore_support_check(self):
        p = self.load_policy({
            **self.related_resource_policy,
            "mode": {
                "type": "config-poll-rule",
                "role": "arn:aws:iam::{account_id}:role/MyRole",
                "schedule": "TwentyFour_Hours",
                "ignore-support-check": True
            }
        })
        p.validate()


class GuardModeTest(BaseTest):

    def test_unsupported_resource(self):
        self.assertRaises(
            ValueError,
            self.load_policy,
            {"name": "vpc", "resource": "vpc", "mode": {"type": "guard-duty"}},
            validate=True,
        )

    def test_lambda_policy_validate_name(self):
        name = "ec2-instance-guard-D8488F01-0E3E-4772-A3CB-E66EEBB9BDF4"
        with self.assertRaises(PolicyValidationError) as e_cm:
            self.load_policy(
                {"name": name,
                 "resource": "ec2",
                 "mode": {"type": "guard-duty"}},
                validate=True)
        self.assertTrue("max length with prefix" in str(e_cm.exception))

    def test_lambda_policy_validate_too_long_description_length(self):
        for description_length in [257, 300, 340]:
            description = 'a' * description_length
            with self.assertRaises(PolicyValidationError) as e_cm:
                self.load_policy(
                    {
                        'name': 'testing',
                        'description': description,
                        'resource': 'ec2',
                        'mode': {'type': 'guard-duty'}
                    },
                    validate=True
                )
            self.assertTrue('max description length of' in str(e_cm.exception))

    def test_lambda_policy_validate_correct_description_length(self):
        for description_length in [0, 1, 128, 256]:
            description = 'a' * description_length
            self.load_policy(
                {
                    'name': 'testing',
                    'description': description,
                    'resource': 'ec2',
                    'mode': {'type': 'guard-duty'}
                },
                validate=True
            )

    def test_lambda_policy_validate_no_description_field(self):
        self.load_policy(
            {
                'name': 'testing',
                'resource': 'ec2',
                'mode': {'type': 'guard-duty'}
            },
            validate=True
        )

    @mock.patch("c7n.mu.LambdaManager.publish")
    def test_ec2_guard_event_pattern(self, publish):

        def assert_publish(policy_lambda, role):
            events = policy_lambda.get_events(mock.MagicMock())
            self.assertEqual(len(events), 1)
            pattern = json.loads(events[0].render_event_pattern())
            expected = {
                "source": ["aws.guardduty"],
                "detail": {"resource": {"resourceType": ["Instance"]}},
                "detail-type": ["GuardDuty Finding"],
            }
            self.assertEqual(pattern, expected)

        publish.side_effect = assert_publish
        p = self.load_policy(
            {
                "name": "ec2-instance-guard",
                "resource": "ec2",
                "mode": {"type": "guard-duty"},
            }
        )
        p.run()

    @mock.patch("c7n.mu.LambdaManager.publish")
    def test_iam_guard_event_pattern(self, publish):

        def assert_publish(policy_lambda, role):
            events = policy_lambda.get_events(mock.MagicMock())
            self.assertEqual(len(events), 1)
            pattern = json.loads(events[0].render_event_pattern())
            expected = {
                "source": ["aws.guardduty"],
                "detail": {"resource": {"resourceType": ["AccessKey"]}},
                "detail-type": ["GuardDuty Finding"],
            }
            self.assertEqual(pattern, expected)

        publish.side_effect = assert_publish
        p = self.load_policy(
            {
                "name": "iam-user-guard",
                "resource": "iam-user",
                "mode": {"type": "guard-duty"},
            }
        )
        p.run()

    @mock.patch("c7n.query.QueryResourceManager.get_resources")
    def test_ec2_instance_guard(self, get_resources):

        def instances(ids, cache=False):
            return [{"InstanceId": ids[0]}]

        get_resources.side_effect = instances

        p = self.load_policy(
            {
                "name": "ec2-instance-guard",
                "resource": "ec2",
                "mode": {"type": "guard-duty"},
            }
        )

        event = event_data("ec2-duty-event.json")
        results = p.push(event, None)
        self.assertEqual(results, [{"InstanceId": "i-99999999"}])

    @mock.patch("c7n.query.QueryResourceManager.get_resources")
    def test_iam_user_access_key_annotate(self, get_resources):

        def users(ids, cache=False):
            return [{"UserName": ids[0]}]

        get_resources.side_effect = users

        p = self.load_policy(
            {
                "name": "user-key-guard",
                "resource": "iam-user",
                "mode": {"type": "guard-duty"},
            }
        )

        event = event_data("iam-duty-event.json")
        results = p.push(event, None)
        self.assertEqual(
            results,
            [
                {
                    u"UserName": u"GeneratedFindingUserName",
                    u"c7n:AccessKeys": {u"AccessKeyId": u"GeneratedFindingAccessKeyId"},
                }
            ],
        )
