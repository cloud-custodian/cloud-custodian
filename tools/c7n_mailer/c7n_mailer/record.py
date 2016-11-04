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
import json
from cStringIO import StringIO


def format_struct(evt):
    io = StringIO()
    json.dump(evt, io, indent=2)
    return io.getvalue()


def resource_tag(resource, k):
    for t in resource.get('Tags', []):
        if t['Key'] == k:
            return t['Value']
    return ''


def resource_owner(resource):
    tags = {t['Key']: t['Value'] for t in resource.get('Tags', [])}
    for k in ('OwnerContact', 'OwnerEID', 'OwnerEmail'):
        if k in tags:
            return tags[k]
    return "Unknown"


def resource_format(resource, resource_type):
    if resource_type == 'ec2':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        return "%s %s %s %s %s %s" % (
            resource['InstanceId'],
            resource.get('VpcId', 'NO VPC!'),
            resource['InstanceType'],
            resource.get('LaunchTime'),
            tag_map.get('Name', ''),
            resource.get('PrivateIpAddress'))
    elif resource_type == 'ami':
        return "%s %s %s" % (
            resource['Name'], resource['ImageId'], resource['CreationDate'])
    elif resource_type == 's3':
        return "%s" % (resource['Name'])
    elif resource_type == 'ebs':
        return "%s %s %s %s" %(
            resource['VolumeId'],
            resource['Size'],
            resource['State'],
            resource['CreateTime'])
    elif resource_type == 'rds':
        return "%s %s %s %s" % (
            resource['DBInstanceIdentifier'],
            "%s-%s" % (
                resource['Engine'], resource['EngineVersion']),
            resource['DBInstanceClass'],
            resource['AllocatedStorage'])
    elif resource_type == 'asg':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        return "%s %s %s" % (
            resource['AutoScalingGroupName'],
            tag_map.get('Name', ''),
            "instances: %d" % (len(resource.get('Instances', []))))
    elif resource_type == 'elb':
        tag_map = {t['Key']: t['Value'] for t in resource.get('Tags', ())}
        if 'ProhibitedPolicies' in resource:
            return "%s %s %s %s" % (
                resource['LoadBalancerName'],
                "instances: %d" % len(resource['Instances']),
                "zones: %d" % len(resource['AvailabilityZones']),
                "prohibited_policies: %s" % ','.join(
                    resource['ProhibitedPolicies']))
        return "%s %s %s" % (
            resource['LoadBalancerName'],
            "instances: %d" % len(resource['Instances']),
            "zones: %d" % len(resource['AvailabilityZones']))
    elif resource_type == 'redshift':
        return "%s %s %s" % (
            resource['ClusterIdentifier'],
            'nodes:%d' % len(resource['ClusterNodes']),
            'encrypted:%s' % resource['Encrypted'])
    elif resource_type == 'emr':
        return "%s status:%s" % (
            resource['Id'],
            resource['Status']['State'])
    elif resource_type == 'cfn':
        return "%s" % (
            resource['StackName'])
    elif resource_type == 'launch-config':
        return "%s" % (
            resource['LaunchConfigurationName'])
    elif resource_type == 'security-group':
        name = resource.get('GroupName', '')
        for t in resource.get('Tags', ()):
            if t['Key'] == 'Name':
                name = t['Value']
        return "%s %s %s inrules: %d outrules: %d" % (
            name,
            resource['GroupId'],
            resource.get('VpcId', 'na'),
            len(resource.get('IpPermissions', ())),
            len(resource.get('IpPermissionsEgress', ())))
    elif resource_type == 'log-group':
        return "name: %s last_write: %s" % (
            resource['logGroupName'],
            resource['lastWrite'])
    elif resource_type == 'cache-cluster':
        return "name: %s created: %s status: %s" % (
            resource['CacheClusterId'],
            resource['CacheClusterCreateTime'],
            resource['CacheClusterStatus'])
    elif resource_type == 'cache-snapshot':
        return "name: %s cluster: %s source: %s" % (
            resource['SnapshotName'],
            resource['CacheClusterId'],
            resource['SnapshotSource'])
    elif resource_type == 'redshift-snapshot':
        return "name: %s db: %s" % (
            resource['SnapshotIdentifier'],
            resource['DBName'])
    elif resource_type == 'ebs-snapshot':
        return "name: %s date: %s" % (
            resource['SnapshotId'],
            resource['StartTime'])
    else:
        print "Unknown resource type", resource_type
        return "%s" % format_struct(resource)
