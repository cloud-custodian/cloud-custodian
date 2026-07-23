# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import jmespath_search, jmespath_compile


class CloudWatchEvents:
    """A mapping of events to resource types."""

    # **These are just shortcuts**, you can use the policy definition to
    # subscribe to any arbitrary cloud trail event that corresponds to
    # a custodian resource.

    # For common events that we want to match, just keep a short mapping.
    # Users can specify arbitrary cloud watch events by specifying these
    # values in their config, but keep the common case simple.

    trail_events = {
        # event source, resource type as keys, mapping to api call and
        # jmespath expression
        'ConsoleLogin': {
            'ids': 'userIdentity.arn',
            'source': 'signin.amazonaws.com'},

        'CreateAutoScalingGroup': {
            'ids': 'requestParameters.autoScalingGroupName',
            'source': 'autoscaling.amazonaws.com'},

        'UpdateAutoScalingGroup': {
            'ids': 'requestParameters.autoScalingGroupName',
            'source': 'autoscaling.amazonaws.com'},

        'CreateBucket': {
            'ids': 'requestParameters.bucketName',
            'source': 's3.amazonaws.com'},

        'CreateCluster': {
            'ids': 'requestParameters.clusterIdentifier',
            'source': 'redshift.amazonaws.com'},

        'CreateLoadBalancer': {
            'ids': 'requestParameters.loadBalancerName',
            'source': 'elasticloadbalancing.amazonaws.com'},

        'CreateLoadBalancerPolicy': {
            'ids': 'requestParameters.loadBalancerName',
            'source': 'elasticloadbalancing.amazonaws.com'},

        'CreateDBInstance': {
            'ids': 'requestParameters.dBInstanceIdentifier',
            'source': 'rds.amazonaws.com'},

        'CreateVolume': {
            'ids': 'responseElements.volumeId',
            'source': 'ec2.amazonaws.com'},

        'SetLoadBalancerPoliciesOfListener': {
            'ids': 'requestParameters.loadBalancerName',
            'source': 'elasticloadbalancing.amazonaws.com'},

        'CreateElasticsearchDomain': {
            'ids': 'requestParameters.domainName',
            'source': 'es.amazonaws.com'},

        'CreateTable': {
            'ids': 'requestParameters.tableName',
            'source': 'dynamodb.amazonaws.com'},

        'CreateDistribution': {
            'ids': 'responseElements.distribution.id',
            'source': 'cloudfront.amazonaws.com'},

        'CreateRepository': {
            'ids': 'responseElements.repositoryMetadata.repositoryName',
            'source': 'codecommit.amazonaws.com'},

        'CreatePipeline': {
            'ids': 'responseElements.pipeline.name',
            'source': 'codepipeline.amazonaws.com'},

        'AllocateAddress': {
            'ids': 'responseElements.publicIp',
            'source': 'ec2.amazonaws.com'},

        'CreateImage': {
            'ids': 'responseElements.imageId',
            'source': 'ec2.amazonaws.com'},

        'CreateSecurityGroup': {
            'ids': 'responseElements.groupId',
            'source': 'ec2.amazonaws.com'},

        'CreateNetworkInterface': {
            'ids': 'responseElements.networkInterface.networkInterfaceId',
            'source': 'ec2.amazonaws.com'},

        'CreateInternetGateway': {
            'ids': 'responseElements.internetGateway.internetGatewayId',
            'source': 'ec2.amazonaws.com'},

        'CreateNatGateway': {
            'ids': 'responseElements.natGateway.natGatewayId',
            'source': 'ec2.amazonaws.com'},

        'CreateFunction': {
            'event': 'CreateFunction20150331',
            'source': 'lambda.amazonaws.com',
            'ids': 'requestParameters.functionName'},

        'RunInstances': {
            'ids': 'responseElements.instancesSet.items[].instanceId',
            'source': 'ec2.amazonaws.com'}}

    @classmethod
    def get(cls, event_name):
        return cls.trail_events.get(event_name)

    @classmethod
    def match(cls, event):
        """Match a given cwe event as cloudtrail with an api call

        That has its information filled out.
        """
        if 'detail' not in event:
            return False
        if 'eventName' not in event['detail']:
            return False
        k = event['detail']['eventName']

        # We want callers to use a compiled expression, but want to avoid
        # initialization cost of doing it without cause. Not thread safe,
        # but usage context is lambda entry.
        if k in cls.trail_events:
            v = dict(cls.trail_events[k])
            if isinstance(v['ids'], str):
                v['ids'] = e = jmespath_compile('detail.%s' % v['ids'])
                cls.trail_events[k]['ids'] = e
            return v

        return False

    @classmethod
    def get_trail_ids(cls, event, mode):
        """extract resources ids from a cloud trail event."""
        resource_ids = ()
        event_name = event['detail']['eventName']
        event_source = event['detail']['eventSource']
        for e in mode.get('events', []):
            if not isinstance(e, dict):
                # Check if we have a short cut / alias
                info = CloudWatchEvents.match(event)
                if info:
                    return info['ids'].search(event)
                continue
            if event_name != e.get('event'):
                continue
            if event_source != e.get('source'):
                continue

            id_query = e.get('ids')
            if not id_query:
                raise ValueError("No id query configured")
            evt = event
            # be forgiving for users specifying with details or without
            if not id_query.startswith('detail.'):
                evt = event.get('detail', {})
            resource_ids = jmespath_search(id_query, evt)
            if resource_ids:
                break
        return resource_ids

    @classmethod
    def get_ids(cls, event, mode):
        mode_type = mode.get('type')
        if mode_type == 'ec2-instance-state':
            resource_ids = [event.get('detail', {}).get('instance-id')]
        elif mode_type == 'asg-instance-state':
            resource_ids = [event.get('detail', {}).get('AutoScalingGroupName')]
        elif mode_type != 'cloudtrail':
            return None
        else:
            resource_ids = cls.get_trail_ids(event, mode)

        if not isinstance(resource_ids, (tuple, list)):
            resource_ids = [resource_ids]

        return list(filter(None, resource_ids))
