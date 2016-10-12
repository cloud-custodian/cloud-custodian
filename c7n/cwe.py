# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import jmespath


class CloudWatchEvents(object):
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
            if isinstance(v['ids'], basestring):
                v['ids'] = e = jmespath.compile('detail.%s' % v['ids'])
                cls.trail_events[k]['ids'] = e
            return v

        return False

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
            info = CloudWatchEvents.match(event)
            if info:
                resource_ids = info['ids'].search(event)
            else:
                for e in mode.get('events', []):
                    if not isinstance(e, dict):
                        continue
                    id_query = e.get('ids')
                    if not id_query:
                        raise ValueError("No id query configured")
                    resource_ids = jmespath.search(
                        id_query, event.get('detail', {}))

        if not isinstance(resource_ids, list):
            resource_ids = [resource_ids]

        return filter(None, resource_ids)
