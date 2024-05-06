# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
import logging

import pytest
from pytest_terraform import terraform

from botocore.exceptions import ClientError
from .common import BaseTest


class Route53HostedZoneTest(BaseTest):

    def test_hostedzone_shield(self):
        session_factory = self.replay_flight_data("test_zone_shield_enable")
        p = self.load_policy(
            {
                "name": "zone-activate",
                "resource": "hostedzone",
                "filters": [
                    {"Config.PrivateZone": False},
                    {"Name": "invitro.cloud."},
                    {"type": "shield-enabled", "state": False},
                ],
                "actions": ["set-shield"],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)
        p = self.load_policy(
            {
                "name": "zone-verify",
                "resource": "hostedzone",
                "filters": [{"type": "shield-enabled", "state": True}],
            },
            session_factory=session_factory,
        )
        self.assertEqual(p.run()[0]["Id"], "/hostedzone/XXXXURLYV5DGGG")
        p = self.load_policy(
            {
                "name": "zone-verify-hostedzone-id",
                "resource": "hostedzone",
                "filters": [{"type": "shield-enabled", "state": False}],
            },
            session_factory=session_factory,
        )
        self.assertEqual(p.run()[0]["c7n:ConfigHostedZoneId"], "XXXXURLYV5DGGG")

    def test_route53_hostedzone_tag(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_tag")

        p = self.load_policy(
            {
                "name": "hostedzone-tag-records",
                "resource": "hostedzone",
                "filters": [
                    {
                        "type": "value",
                        "key": "ResourceRecordSetCount",
                        "value": 2,
                        "op": "gte",
                    }
                ],
                "actions": [{"type": "tag", "key": "abc", "value": "xyz"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 1)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_hostedzone_untag(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_untag")

        p = self.load_policy(
            {
                "name": "hostedzone-untag-records",
                "resource": "hostedzone",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["abc"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 0)

    def test_route53_hostedzone_markop(self):
        session_factory = self.replay_flight_data("test_route53_hostedzone_markop")

        p = self.load_policy(
            {
                "name": "hostedzone-markop-records",
                "resource": "hostedzone",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "days": 4}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 2)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())


@pytest.mark.audited
@terraform('route53_hostedzone_delete', teardown=terraform.TEARDOWN_IGNORE)
def test_route53_hostedzone_delete(test, route53_hostedzone_delete):
    session_factory = test.replay_flight_data("test_route53_hostedzone_delete")
    client = session_factory().client("route53")
    pdata = {
        "name": "r53domain-delete-hostedzone",
        "resource": "hostedzone",
        "filters": [{"tag:TestTag": "present"}],
        "actions": ["delete"]}

    output = test.capture_logging('custodian.actions', level=logging.WARNING)

    p = test.load_policy(pdata, session_factory=session_factory)
    with pytest.raises(ClientError) as ecm:
        p.run()
    assert ecm.value.response['Error']['Code'] == 'HostedZoneNotEmpty'
    assert "set force to remove all records in zone" in output.getvalue()

    pdata['actions'] = [{'type': 'delete', 'force': True}]
    p = test.load_policy(pdata, session_factory=session_factory)
    p.run()

    if test.recording:
        time.sleep(3)

    assert client.list_hosted_zones_by_name(
        DNSName=route53_hostedzone_delete['aws_route53_zone.test_hosted_zone.name']
    ).get('HostedZones') == []


class Route53HealthCheckTest(BaseTest):

    def test_route53_healthcheck_tag(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_tag")

        p = self.load_policy(
            {
                "name": "healthcheck-tag-records",
                "resource": "healthcheck",
                "filters": [
                    {
                        "type": "value",
                        "key": "HealthCheckConfig.FailureThreshold",
                        "value": 3,
                        "op": "gte",
                    }
                ],
                "actions": [{"type": "tag", "key": "abc", "value": "xyz"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        tags = client.list_tags_for_resource(
            ResourceType="healthcheck", ResourceId=resources[0]["Id"]
        )
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 2)
        self.assertTrue("abc" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_healthcheck_untag(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_untag")

        p = self.load_policy(
            {
                "name": "healthcheck-untag-records",
                "resource": "healthcheck",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["abc"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        tags = client.list_tags_for_resource(
            ResourceType="healthcheck", ResourceId=resources[0]["Id"]
        )
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 1)  # Name is a tag
        self.assertTrue("Name" in tags["ResourceTagSet"]["Tags"][0].values())

    def test_route53_healthcheck_markop(self):
        session_factory = self.replay_flight_data("test_route53_healthcheck_markop")

        p = self.load_policy(
            {
                "name": "healthcheck-markop-records",
                "resource": "healthcheck",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "days": 4}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("route53")
        _id = resources[0]["Id"].split("/")[-1]
        tags = client.list_tags_for_resource(ResourceType="healthcheck", ResourceId=_id)
        self.assertEqual(len(tags["ResourceTagSet"]["Tags"]), 3)
        self.assertTrue("maid_status" in tags["ResourceTagSet"]["Tags"][1].values())


class Route53DomainTest(BaseTest):

    def test_route53_domain_auto_renew(self):
        session_factory = self.replay_flight_data("test_route53_domain")
        p = self.load_policy(
            {
                "name": "r53domain-auto-renew",
                "resource": "r53domain",
                "filters": [{"type": "value", "key": "AutoRenew", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_transfer_lock(self):
        session_factory = self.replay_flight_data("test_route53_domain")
        p = self.load_policy(
            {
                "name": "r53domain-transfer-lock",
                "resource": "r53domain",
                "filters": [{"type": "value", "key": "TransferLock", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_route53_domain_add_tag(self):
        session_factory = self.replay_flight_data("test_route53_domain_add_tag")
        p = self.load_policy(
            {
                "name": "r53domain-add-tag",
                "resource": "r53domain",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "tag", "key": "TestTag", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("route53domains")
        tags = client.list_tags_for_domain(DomainName=resources[0]["DomainName"])[
            "TagList"
        ]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["TestTag", "TestValue"])

    def test_route53_domain_remove_tag(self):
        session_factory = self.replay_flight_data("test_route53_domain_remove_tag")
        p = self.load_policy(
            {
                "name": "r53domain-add-tag",
                "resource": "r53domain",
                "filters": [{"tag:TestTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("route53domains")
        tags = client.list_tags_for_domain(DomainName=resources[0]["DomainName"])[
            "TagList"
        ]
        self.assertEqual(len(tags), 0)


class ResourceRecordSetTest(BaseTest):
    def test_resourcerecordset_remove(self):
        session_factory = self.replay_flight_data(
            'test_r53_resourcerecordset_remove')
        p = self.load_policy({
            "name": "r53domain-remove-recordsets",
            "resource": "rrset",
            "filters": [{
                'type': 'value',
                'key': 'AliasTarget.DNSName',
                'value': 'vpce-12345abcdefgh-mxpozkdy.us-west-2.vpce.amazonaws.com.',
                }],
            "actions": ["delete"]},
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        client = session_factory().client("route53")
        records = client.list_resource_record_sets(
            HostedZoneId=resources[0]["c7n:parent-id"]
        )
        self.assertEqual(len(records["ResourceRecordSets"]), 3)

    def test_resourcerecordset_cname_remove(self):
        session_factory = self.replay_flight_data(
            'test_r53_resourcerecordset_cname_remove')
        p = self.load_policy({
            "name": "r53domain-remove-cname-recordsets",
            "resource": "rrset",
            "filters": [{
                'type': 'value',
                'key': 'ResourceRecords[].Value',
                'op': 'intersect',
                'value': ['mailserver01.subdomain.example.com.'],
                }],
            "actions": ["delete"]},
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        client = session_factory().client("route53")
        records = client.list_resource_record_sets(
            HostedZoneId=resources[0]["c7n:parent-id"]
        )
        self.assertEqual(len(records["ResourceRecordSets"]), 2)


class Route53EnableDNSQueryLoggingTest(BaseTest):

    def test_hostedzone_set_query_log(self):
        session_factory = self.replay_flight_data(
            'test_route53_enable_query_logging')
        p = self.load_policy({
            'name': 'enablednsquerylogging',
            'resource': 'hostedzone',
            'filters': [
                {'Config.PrivateZone': False},
                {'type': 'query-logging-enabled', 'state': False}],
            'actions': [{
                'type': 'set-query-logging',
                'log-group': '/aws/route53/cloudcustodian.io',
                'state': True,
                'set-permissions': True}]},
            session_factory=session_factory, config={'account_id': '644160558196'})
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('route53')
        enabled_zones = {
            c['HostedZoneId']: c for c in
            client.list_query_logging_configs().get('QueryLoggingConfigs')}

        for r in resources:
            self.assertTrue(r['Id'].rsplit('/', 1)[-1] in enabled_zones)

    def test_hostedzone_filter_query_log(self):
        session_factory = self.replay_flight_data(
            'test_route53_filter_query_logging')
        p = self.load_policy({
            'name': 'query-logging-enabled',
            'resource': 'hostedzone',
            'filters': [{'type': 'query-logging-enabled', 'state': True}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], "/hostedzone/Z0423603VKO3K9HA5YQD")
        self.assertEqual(resources[0]['c7n:log-config']['loggroup_subscription'][0]['logGroupName'],
                         '/aws/route53/custodian.io')


class TestResolverQueryLogConfig(BaseTest):

    def test_resolver_query_log_config(self):
        session_factory = self.replay_flight_data(
            'test_resolver_query_log_config')
        p = self.load_policy({
            'name': 'r53-resolver-query-log-config',
            'resource': 'resolver-logs',
            'filters': [
                {'type': 'value', 'key': 'Name', 'op': 'eq', 'value': 'Test-rqlc'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_resolver_query_log_config_vpc_filter(self):
        session_factory = self.replay_flight_data(
            'test_resolver_query_log_config_vpc_filter')
        p = self.load_policy({
            'name': 'r53-resolver-query-log-config-vpc-filter',
            'resource': 'resolver-logs',
            'filters': [
                {'type': 'is-associated', 'vpcid': 'vpc-011516c4325953'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_resolver_query_log_config_associate_1(self):
        session_factory = self.replay_flight_data(
            'test_resolver_query_log_config_associate')
        p = self.load_policy({
            'name': 'r53-resolver-query-log-config-associate-1',
            'resource': 'resolver-logs',
            'filters': [
                {'type': 'value', 'key': 'Name', 'op': 'eq', 'value': 'Test-rqlc'}],
            'actions': [{
                'type': 'associate-vpc', 'vpcid': 'all'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], "rqlc-fb017689395648d1")

    def test_resolver_query_log_config_associate_2(self):
        session_factory = self.replay_flight_data(
            'test_resolver_query_log_config_associate_2')
        p = self.load_policy({
            'name': 'r53-resolver-query-log-config-associate-2',
            'resource': 'resolver-logs',
            'filters': [
                {'type': 'value', 'key': 'Name', 'op': 'eq', 'value': 'Test-rqlc-2'}],
            'actions': [{
                'type': 'associate-vpc', 'vpcid': 'vpc-01234567891234'}]},
            session_factory=session_factory)
        resources = p.run()

        client = session_factory().client("route53resolver")
        rqlca = client.list_resolver_query_log_config_associations()
        self.assertEqual(rqlca[
            'ResolverQueryLogConfigAssociations'][0]['ResourceId'], "vpc-01234567891234")
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], "rqlc-01234567891234")

    def test_resolver_query_log_config_not_associated(self):
        session_factory = self.replay_flight_data(
            'test_resolver_query_log_config_associate_2')
        p = self.load_policy({
            'name': 'r53-resolver-query-log-config-not-associated',
            'resource': 'resolver-logs',
            'filters': [{
                'not': [{'type': 'is-associated', 'vpcid': 'vpc-0123456789123'}]}]},
            session_factory=session_factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Id'], "rqlc-01234567891234")


class Route53RecoveryReadinessCheckTest(BaseTest):

    def test_readiness_check_add_tag(self):
        session_factory = self.replay_flight_data("test_readiness_check_add_tag",)
        p = self.load_policy(
            {
                "name": "readiness-check-add-tag",
                "resource": "readiness-check",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "tag", "key": "TestTag", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-readiness")
        tags = client.list_tags_for_resources(ResourceArn=resources[0]["ReadinessCheckArn"])['Tags']
        self.assertEqual(tags, {"TestTag": "TestValue"})

    def test_readiness_check_remove_tag(self):
        session_factory = self.replay_flight_data("test_readiness_check_remove_tag",)
        p = self.load_policy(
            {
                "name": "readiness-check-remove-tag",
                "resource": "readiness-check",
                "filters": [{"tag:TestTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-readiness")
        tags = client.list_tags_for_resources(ResourceArn=resources[0]["ReadinessCheckArn"])['Tags']
        self.assertEqual(len(tags), 0)

    def test_readiness_check_markop(self):
        session_factory = self.replay_flight_data("test_readiness_check_markop")
        p = self.load_policy(
            {
                "name": "readiness-check-markop",
                "resource": "readiness-check",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "tag": "TestTag", "days": 2}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-readiness")
        tags = client.list_tags_for_resources(ResourceArn=resources[0]["ReadinessCheckArn"])['Tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'TestTag': 'Resource does not meet policy: notify@2023/02/22'})

    def test_readiness_check_markedforop(self):
        session_factory = self.replay_flight_data("test_readiness_check_marked_for_op")
        p = self.load_policy(
            {
                "name": "readiness-check-markedforop",
                "resource": "readiness-check",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "TestTag",
                        "op": "notify",
                        "skew": 3,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_readiness_cross_account(self):
        session_factory = self.replay_flight_data("test_readiness_cross_account")
        p = self.load_policy(
            {
                "name": "readiness-cross-account",
                "resource": "readiness-check",
                "filters": [
                    {
                        'type': 'cross-account',
                        "whitelist": ["111111111111"]
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:CrossAccountViolations'], ['222222222222'])


class Route53RecoveryClusterTest(BaseTest):

    def test_recovery_cluster_add_tag(self):
        session_factory = self.replay_flight_data("test_recovery_cluster_add_tag",)
        p = self.load_policy(
            {
                "name": "recovery-cluster-add-tag",
                "resource": "recovery-cluster",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "tag", "key": "TestTag", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-control-config")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["ClusterArn"])['Tags']
        self.assertEqual(tags, {"TestTag": "TestValue"})

    def test_recovery_cluster_remove_tag(self):
        session_factory = self.replay_flight_data("test_recovery_cluster_remove_tag",)
        p = self.load_policy(
            {
                "name": "recovery-cluster-remove-tag",
                "resource": "recovery-cluster",
                "filters": [{"tag:TestTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-control-config")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["ClusterArn"])['Tags']
        self.assertEqual(len(tags), 0)


class TestControlPanel(BaseTest):

    def test_control_panel_resource(self):
        session_factory = self.replay_flight_data("test_control_panel")
        p = self.load_policy(
            {
                "name": "all-control-panels",
                "resource": "recovery-control-panel",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_control_panel_add_tag(self):
        session_factory = self.replay_flight_data("test_control_panel_add_tag",)
        p = self.load_policy(
            {
                "name": "control-panel-add-tag",
                "resource": "recovery-control-panel",
                "filters": [{"tag:TestTag": "absent"}],
                "actions": [{"type": "tag", "key": "TestTag", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-control-config")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["ControlPanelArn"])['Tags']
        self.assertEqual(tags, {"TestTag": "TestValue"})

    def test_control_panel_remove_tag(self):
        session_factory = self.replay_flight_data("test_control_panel_remove_tag",)
        p = self.load_policy(
            {
                "name": "control-panel-remove-tag",
                "resource": "recovery-control-panel",
                "filters": [{"tag:TestTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-west-2").client("route53-recovery-control-config")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["ControlPanelArn"])['Tags']
        self.assertEqual(len(tags), 0)

    def test_control_panel_safety_rule_filter(self):
        session_factory = self.replay_flight_data("test_control_panel_safety_rule_filter",)
        p = self.load_policy(
            {
                "name": "control-panel-safety-rule",
                "resource": "recovery-control-panel",
                "filters": [{'type': 'safety-rule', 'count': 1, 'count_op': 'gte'}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ControlPanelArn'],
            'arn:aws:route53-recovery-control::644160558196:controlpanel/fd5a6bfc73364a0dbd48d3915867a306')
