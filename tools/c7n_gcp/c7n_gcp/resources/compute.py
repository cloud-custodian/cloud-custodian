# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re

from datetime import datetime

from c7n.utils import local_session, type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.filters.iampolicy import IamPolicyValueFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo

from c7n.filters.core import ValueFilter
from c7n.filters.offhours import OffHour, OnHour


@resources.register('instance')
class Instance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'instances'
        enum_spec = ('aggregatedList', 'items.*.instances[]', None)
        scope = 'project'
        name = id = 'name'
        labels = True
        default_report_fields = ['name', 'status', 'creationTimestamp', 'machineType', 'zone']
        asset_type = "compute.googleapis.com/Instance"
        scc_type = "google.compute.Instance"
        metric_key = 'metric.labels.instance_name'
        urn_component = "instance"
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            # The api docs for compute instance get are wrong,
            # they spell instance as resourceId
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'zone': resource_info['zone'],
                        'instance': resource_info[
                            'resourceName'].rsplit('/', 1)[-1]})

        @staticmethod
        def get_label_params(resource, all_labels):
            project, zone, instance = re.match(
                '.*?/projects/(.*?)/zones/(.*?)/instances/(.*)',
                resource['selfLink']).groups()
            return {'project': project, 'zone': zone, 'instance': instance,
                    'body': {
                        'labels': all_labels,
                        'labelFingerprint': resource['labelFingerprint']
                    }}

        @classmethod
        def refresh(cls, client, resource):
            project, zone, name = re.match(
                '.*?/projects/(.*?)/zones/(.*?)/instances/(.*)',
                resource['selfLink']).groups()
            return cls.get(
                client,
                {
                    'project_id': project,
                    'zone': zone,
                    'resourceName': name
                }
            )


Instance.filter_registry.register('offhour', OffHour)
Instance.filter_registry.register('onhour', OnHour)

@Instance.filter_registry.register('boot-disk-source-image')
class BootDiskSourceImage(ValueFilter):
    """Filters instances by their boot disk's source image
    See https://cloud.google.com/compute/docs/reference/rest/v1/images/get for valid fields.

    :example:

    Filter all instances that have a source boot disk image older than 1 year

    .. code-block:: yaml

        policies:
          - name: find-instances-with-old-boot-images
            resource: gcp.instance
            filters:
              - type: boot-disk-source-image
                key: creationTimestamp
                op: greater-than
                value_type: age
                value: 365
    """

    schema = type_schema('boot-disk-source-image', rinherit=ValueFilter.schema)
    permissions = ('compute.images.get',)

    def get_resource_params(self, resource):
        path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/instances/.*')
        project, zone = path_param_re.match(resource['selfLink']).groups()
        return {'project': project, 'zone': zone, 'instance': resource["name"]}
    
    def process_resource(self, resource, event=None):
        session = local_session(self.manager.session_factory)
        model = self.manager.get_model()
        params = self.get_resource_params(resource)
        boot_disk_images = []
        disk_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/disks/(.*?)$')
        image_param_re = re.compile('.*?/projects/(.*?)/global/images/(.*?)$')
        for disk in resource["disks"]:
            if disk["boot"] == True :
                boot_disk_project, boot_disk_zone, boot_disk_name = disk_param_re.match(disk["source"]).groups()
                boot_disk = Disk.resource_type.get(session.client(
                    model.service, model.version, "disks"), {'project_id': boot_disk_project, 'zone': boot_disk_zone, 'disk_id': boot_disk_name})
                image_project, image_name = image_param_re.match(boot_disk["sourceImage"]).groups()
                boot_disk_image = Image.resource_type.get(session.client(
                    model.service, model.version, "images"), {'project_id': image_project, 'image_id': image_name})
                boot_disk_images.append(boot_disk_image)
        return super(BootDiskSourceImage, self).process(boot_disk_images, None)
    
    def get_client(self, session, model):
        return session.client(
            model.service, model.version, model.component)
    
    def process(self, resources, event=None):
        return [r for r in resources if self.process_resource(r)]


@Instance.filter_registry.register('effective-firewall')
class EffectiveFirewall(ValueFilter):
    """Filters instances by their effective firewall rules.
    See `getEffectiveFirewalls
    <https://cloud.google.com/compute/docs/reference/rest/v1/instances/getEffectiveFirewalls>`_
    for valid fields.

    :example:

    Filter all instances that have a firewall rule that allows public
    acess

    .. code-block:: yaml

        policies:
           - name: find-publicly-accessable-instances
             resource: gcp.instance
             filters:
             - type: effective-firewall
               key: firewalls[*].sourceRanges[]
               op: contains
               value: "0.0.0.0/0"
    """

    schema = type_schema('effective-firewall', rinherit=ValueFilter.schema)
    permissions = ('compute.instances.getEffectiveFirewalls',)

    def get_resource_params(self, resource):
        path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/instances/.*')
        project, zone = path_param_re.match(resource['selfLink']).groups()
        return {'project': project, 'zone': zone, 'instance': resource["name"]}

    def process_resource(self, client, resource):
        params = self.get_resource_params(resource)
        effective_firewalls = []
        for interface in resource["networkInterfaces"]:
            effective_firewalls.append(client.execute_command(
                'getEffectiveFirewalls', {"networkInterface": interface["name"], **params}))
        return super(EffectiveFirewall, self).process(effective_firewalls, None)

    def get_client(self, session, model):
        return session.client(
            model.service, model.version, model.component)

    def process(self, resources, event=None):
        model = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = self.get_client(session, model)
        return [r for r in resources if self.process_resource(client, r)]


class InstanceAction(MethodAction):

    def get_resource_params(self, model, resource):
        path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/instances/(.*)')
        project, zone, instance = path_param_re.match(resource['selfLink']).groups()
        return {'project': project, 'zone': zone, 'instance': instance}


@Instance.action_registry.register('start')
class Start(InstanceAction):

    schema = type_schema('start')
    method_spec = {'op': 'start'}
    attr_filter = ('status', ('TERMINATED',))


@Instance.action_registry.register('stop')
class Stop(InstanceAction):
    """
    Caution: `stop` in GCP is closer to terminate in terms of effect.

    `suspend` is closer to stop in other providers.

    See https://cloud.google.com/compute/docs/instances/instance-life-cycle
    """

    schema = type_schema('stop')
    method_spec = {'op': 'stop'}
    attr_filter = ('status', ('RUNNING',))


@Instance.action_registry.register('suspend')
class Suspend(InstanceAction):

    schema = type_schema('suspend')
    method_spec = {'op': 'suspend'}
    attr_filter = ('status', ('RUNNING',))


@Instance.action_registry.register('resume')
class Resume(InstanceAction):

    schema = type_schema('resume')
    method_spec = {'op': 'resume'}
    attr_filter = ('status', ('SUSPENDED',))


@Instance.action_registry.register('delete')
class Delete(InstanceAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}


@Instance.action_registry.register('detach-disks')
class DetachDisks(MethodAction):
    """
    `Detaches <https://cloud.google.com/compute/docs/reference/rest/v1/instances/detachDisk>`_
    all disks from instance. The action does not specify any parameters.

    It may be useful to be used before deleting instances to not delete disks
    that are set to auto delete.

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-instance-detach-disks
            resource: gcp.instance
            filters:
              - type: value
                key: name
                value: instance-template-to-detahc
            actions:
              - type: detach-disks
    """
    schema = type_schema('detach-disks')
    attr_filter = ('status', ('TERMINATED',))
    method_spec = {'op': 'detachDisk'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/zones/(.*?)/instances/(.*)')

    def validate(self):
        pass

    def process_resource_set(self, client, model, resources):
        for resource in resources:
            self.process_resource(client, resource)

    def process_resource(self, client, resource):
        op_name = 'detachDisk'

        project, zone, instance = self.path_param_re.match(
            resource['selfLink']).groups()

        base_params = {'project': project, 'zone': zone, 'instance': instance}
        for disk in resource.get('disks', []):
            params = dict(base_params, deviceName=disk['deviceName'])
            self.invoke_api(client, op_name, params)


@Instance.action_registry.register('create-machine-image')
class CreateMachineImage(MethodAction):
    """
    `Creates <https://cloud.google.com/compute/docs/reference/rest/beta/machineImages/insert>`_
     Machine Image from instance.

    The `name_format` specifies name of image in python `format string <https://pyformat.info/>`

    Inside format string there are defined variables:
      - `now`: current time
      - `instance`: whole instance resource

    Default name format is `{instance[name]}`

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-create-machine-image
            resource: gcp.instance
            filters:
              - type: value
                key: name
                value: instance-create-to-make-image
            actions:
              - type: create-machine-image
                name_format: "{instance[name]:.50}-{now:%Y-%m-%d}"

    """
    schema = type_schema('create-machine-image', name_format={'type': 'string'})
    method_spec = {'op': 'insert'}
    permissions = ('compute.machineImages.create',)

    def get_resource_params(self, model, resource):
        path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/instances/(.*)')
        project, _, _ = path_param_re.match(resource['selfLink']).groups()
        name_format = self.data.get('name_format', '{instance[name]}')
        name = name_format.format(instance=resource, now=datetime.now())

        return {'project': project, 'sourceInstance': resource['selfLink'], 'body': {'name': name}}

    def get_client(self, session, model):
        return session.client(model.service, "beta", "machineImages")


@resources.register('image')
class Image(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'images'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "sourceType", "status", "creationTimestamp",
            "diskSizeGb", "family"]
        asset_type = "compute.googleapis.com/Image"
        urn_component = "image"
        labels = True

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'image': resource_info['image_id']})

        @staticmethod
        def get_label_params(resource, all_labels):
            project, resource_id = re.match(
                '.*?/projects/(.*?)/global/images/(.*)',
                resource['selfLink']).groups()
            return {'project': project, 'resource': resource_id,
                    'body': {
                        'labels': all_labels,
                        'labelFingerprint': resource['labelFingerprint']
                    }}

        @classmethod
        def refresh(cls, client, resource):
            project, resource_id = re.match(
                '.*?/projects/(.*?)/global/images/(.*)',
                resource['selfLink']).groups()
            return cls.get(
                client,
                {
                    'project_id': project,
                    'image_id': resource_id
                }
            )


@Image.filter_registry.register('iam-policy')
class ImageIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process images resources correctly.
    """
    permissions = ('compute.images.getIamPolicy',)

    def _verb_arguments(self, resource):
        project, _ = re.match(
            '.*?/projects/(.*?)/global/images/(.*)',
            resource['selfLink']).groups()
        verb_arguments = {'resource': resource[self.manager.resource_type.id], 'project': project}
        return verb_arguments

    def process_resources(self, resources):
        value_filter = IamPolicyValueFilter(self.data['doc'], self.manager)
        value_filter._verb_arguments = self._verb_arguments
        return value_filter.process(resources)


@Image.action_registry.register('delete')
class DeleteImage(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    attr_filter = ('status', ('READY'))
    path_param_re = re.compile('.*?/projects/(.*?)/global/images/(.*)')

    def get_resource_params(self, m, r):
        project, image_id = self.path_param_re.match(r['selfLink']).groups()
        return {'project': project, 'image': image_id}

@resources.register('image')
class Image(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'images'
        scope = 'zone'
        enum_spec = ('aggregatedList', 'items.*.images[]', None)
        name = id = 'name'
        labels = True
        default_report_fields = ["name", "status", "diskSizeGb"]
        asset_type = "compute.googleapis.com/Images"
        urn_component = "image"
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'image': resource_info['image_id']})

        @staticmethod
        def get_label_params(resource, all_labels):
            disk_image_param_re = re.compile('.*?/projects/(.*?)/global/images/(.*?)$')
            project, image = disk_image_param_re.match(
                resource['selfLink']).groups()
            return {'project': project, 'resource': image,
                    'body': {
                        'labels': all_labels,
                        'labelFingerprint': resource['labelFingerprint']
                    }}

@resources.register('disk')
class Disk(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'disks'
        scope = 'zone'
        enum_spec = ('aggregatedList', 'items.*.disks[]', None)
        name = id = 'name'
        labels = True
        default_report_fields = ["name", "sizeGb", "status", "zone"]
        asset_type = "compute.googleapis.com/Disk"
        urn_component = "disk"
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'zone': resource_info['zone'],
                        'disk': resource_info['disk_id']})

        @staticmethod
        def get_label_params(resource, all_labels):
            path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/disks/(.*)')
            project, zone, instance = path_param_re.match(
                resource['selfLink']).groups()
            return {'project': project, 'zone': zone, 'resource': instance,
                    'body': {
                        'labels': all_labels,
                        'labelFingerprint': resource['labelFingerprint']
                    }}


@Disk.action_registry.register('snapshot')
class DiskSnapshot(MethodAction):
    """
    `Snapshots <https://cloud.google.com/compute/docs/reference/rest/v1/disks/createSnapshot>`_
    disk.

    The `name_format` specifies name of snapshot in python `format string <https://pyformat.info/>`

    Inside format string there are defined variables:
      - `now`: current time
      - `disk`: whole disk resource

    Default name format is `{disk.name}`

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-disk-snapshot
            resource: gcp.disk
            filters:
              - type: value
                key: name
                value: disk-7
            actions:
              - type: snapshot
                name_format: "{disk[name]:.50}-{now:%Y-%m-%d}"
    """
    schema = type_schema('snapshot', name_format={'type': 'string'})
    method_spec = {'op': 'createSnapshot'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/zones/(.*?)/disks/(.*)')
    attr_filter = ('status', ('RUNNING', 'READY'))

    def get_resource_params(self, model, resource):
        project, zone, resourceId = self.path_param_re.match(resource['selfLink']).groups()
        name_format = self.data.get('name_format', '{disk[name]}')
        name = name_format.format(disk=resource, now=datetime.now())

        return {
            'project': project,
            'zone': zone,
            'disk': resourceId,
            'body': {
                'name': name,
                'labels': resource.get('labels', {}),
            }
        }


@Disk.action_registry.register('delete')
class DiskDelete(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/zones/(.*?)/disks/(.*)')
    attr_filter = ('status', ('RUNNING', 'READY'))

    def get_resource_params(self, m, r):
        project, zone, resourceId = self.path_param_re.match(r['selfLink']).groups()
        return {
            'project': project,
            'zone': zone,
            'disk': resourceId,
        }


@resources.register('snapshot')
class Snapshot(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'snapshots'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        default_report_fields = ["name", "status", "diskSizeGb", "creationTimestamp"]
        asset_type = "compute.googleapis.com/Snapshot"
        urn_component = "snapshot"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'snapshot': resource_info['snapshot_id']})


@Snapshot.action_registry.register('delete')
class DeleteSnapshot(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    attr_filter = ('status', ('READY', 'UPLOADING'))
    path_param_re = re.compile('.*?/projects/(.*?)/global/snapshots/(.*)')

    def get_resource_params(self, m, r):
        project, snapshot_id = self.path_param_re.match(r['selfLink']).groups()
        # Docs are wrong :-(
        # https://cloud.google.com/compute/docs/reference/rest/v1/snapshots/delete
        return {'project': project, 'snapshot': snapshot_id}


@resources.register('instance-template')
class InstanceTemplate(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/instanceTemplates"""
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'instanceTemplates'
        scope = 'zone'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        default_report_fields = [
            name, "description", "creationTimestamp",
            "properties.machineType", "properties.description"]
        asset_type = "compute.googleapis.com/InstanceTemplate"
        urn_component = "instance-template"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'instanceTemplate': resource_info['instance_template_name']})


@InstanceTemplate.action_registry.register('delete')
class InstanceTemplateDelete(MethodAction):
    """
    `Deletes <https://cloud.google.com/compute/docs/reference/rest/v1/instanceTemplates/delete>`_
    an Instance Template. The action does not specify any parameters.

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-instance-template-delete
            resource: gcp.instance-template
            filters:
              - type: value
                key: name
                value: instance-template-to-delete
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        project, instance_template = re.match('.*/projects/(.*?)/.*/instanceTemplates/(.*)',
                                              r['selfLink']).groups()
        return {'project': project,
                'instanceTemplate': instance_template}


@resources.register('autoscaler')
class Autoscaler(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/autoscalers"""
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'autoscalers'
        name = id = 'name'
        enum_spec = ('aggregatedList', 'items.*.autoscalers[]', None)
        default_report_fields = [
            "name", "description", "status", "target", "recommendedSize"]
        asset_type = "compute.googleapis.com/Autoscaler"
        metric_key = "resource.labels.autoscaler_name"
        urn_component = "autoscaler"
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            project, zone, autoscaler = re.match(
                'projects/(.*?)/zones/(.*?)/autoscalers/(.*)',
                resource_info['resourceName']).groups()

            return client.execute_command(
                'get', {'project': project,
                        'zone': zone,
                        'autoscaler': autoscaler})


@Autoscaler.action_registry.register('set')
class AutoscalerSet(MethodAction):
    """
    `Patches <https://cloud.google.com/compute/docs/reference/rest/v1/autoscalers/patch>`_
    configuration parameters for the autoscaling algorithm.

    The `coolDownPeriodSec` specifies the number of seconds that the autoscaler
    should wait before it starts collecting information from a new instance.

    The `cpuUtilization.utilizationTarget` specifies the target CPU utilization that the
    autoscaler should maintain.

    The `loadBalancingUtilization.utilizationTarget` specifies fraction of backend capacity
    utilization (set in HTTP(S) load balancing configuration) that autoscaler should maintain.

    The `minNumReplicas` specifies the minimum number of replicas that the autoscaler can
    scale down to.

    The `maxNumReplicas` specifies the maximum number of instances that the autoscaler can
    scale up to.

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-autoscaler-set
            resource: gcp.autoscaler
            filters:
              - type: value
                key: name
                value: instance-group-2
            actions:
              - type: set
                coolDownPeriodSec: 20
                cpuUtilization:
                  utilizationTarget: 0.7
                loadBalancingUtilization:
                  utilizationTarget: 0.7
                minNumReplicas: 1
                maxNumReplicas: 4
    """
    schema = type_schema('set',
                         **{
                             'coolDownPeriodSec': {
                                 'type': 'integer',
                                 'minimum': 15
                             },
                             'cpuUtilization': {
                                 'type': 'object',
                                 'required': ['utilizationTarget'],
                                 'properties': {
                                     'utilizationTarget': {
                                         'type': 'number',
                                         'exclusiveMinimum': 0,
                                         'maximum': 1
                                     }
                                 },
                             },
                             'loadBalancingUtilization': {
                                 'type': 'object',
                                 'required': ['utilizationTarget'],
                                 'properties': {
                                     'utilizationTarget': {
                                         'type': 'number',
                                         'exclusiveMinimum': 0,
                                         'maximum': 1
                                     }
                                 }
                             },
                             'maxNumReplicas': {
                                 'type': 'integer',
                                 'exclusiveMinimum': 0
                             },
                             'minNumReplicas': {
                                 'type': 'integer',
                                 'exclusiveMinimum': 0
                             }
                         })
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/zones/(.*?)/autoscalers/(.*)')
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        project, zone, autoscaler = self.path_param_re.match(resource['selfLink']).groups()
        body = {}

        if 'coolDownPeriodSec' in self.data:
            body['coolDownPeriodSec'] = self.data['coolDownPeriodSec']

        if 'cpuUtilization' in self.data:
            body['cpuUtilization'] = self.data['cpuUtilization']

        if 'loadBalancingUtilization' in self.data:
            body['loadBalancingUtilization'] = self.data['loadBalancingUtilization']

        if 'maxNumReplicas' in self.data:
            body['maxNumReplicas'] = self.data['maxNumReplicas']

        if 'minNumReplicas' in self.data:
            body['minNumReplicas'] = self.data['minNumReplicas']

        result = {'project': project,
                  'zone': zone,
                  'autoscaler': autoscaler,
                  'body': {
                      'autoscalingPolicy': body
                  }}

        return result


@resources.register('zone')
class Zone(QueryResourceManager):
    """GC resource: https://cloud.google.com/compute/docs/reference/rest/v1/zones"""
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'zones'
        enum_spec = ('list', 'items[]', None)
        scope = 'project'
        name = id = 'name'
        default_report_fields = ['id', 'name', 'dnsName', 'creationTime', 'visibility']
        asset_type = "compute.googleapis.com/compute"
        scc_type = "google.cloud.dns.ManagedZone"


@resources.register('compute-project')
class Project(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/projects"""
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'projects'
        enum_spec = ('get', '[@]', None)
        name = id = 'name'
        default_report_fields = ["name"]
        asset_type = 'compute.googleapis.com/Project'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id']})


@resources.register('instance-group-manager')
class InstanceGroupManager(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'instanceGroupManagers'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        parent_spec = {
            'resource': 'zone',
            'child_enum_params': {
                ('name', 'zone')},
            'use_child_query': False,
        }
        default_report_fields = ['id', 'name', 'dnsName', 'creationTime', 'visibility']
