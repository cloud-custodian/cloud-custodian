# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_openstack.query import QueryResourceManager, TypeInfo
from c7n_openstack.provider import resources
from c7n.utils import local_session
from c7n.utils import type_schema
from c7n.filters import Filter
from c7n.filters import AgeFilter, ListItemFilter


@resources.register('server')
class Server(QueryResourceManager):
    class resource_type(TypeInfo):
        enum_spec = ('list_servers', None)
        id = 'id'
        name = 'name'

        set_server_metadata = "set_server_metadata"
        delete_server_metadata = "delete_server_metadata"
        add_server_tag = "add_server_tag"
        set_server_tag = "set_server_tag"
        delete_server_tag = "delete_server_tag"

        default_report_fields = ['id', 'name', 'status', 'tenant_id']


@Server.filter_registry.register('image')
class ImageFilter(Filter):
    """Filters Servers based on their image attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: dns-hostname-enabled
                resource: vpc
                filters:
                  - type: image
                    image_name: test-image
    """
    schema = type_schema(
        'image',
        image_name={'type': 'string'},
        visibility={'type': 'string'},
        status={'type': 'string'})

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client()
        image_name = self.data.get('image_name', None)
        visibility = self.data.get('visibility', None)
        status = self.data.get('status', None)

        images = client.list_images()
        for r in resources:
            image = find_object_by_property(images, 'id', r.image.id)
            matched = True
            if not image:
                if status == "absent":
                    results.append(r)
                continue
            if image_name is not None and image_name != image.name:
                matched = False
            if visibility is not None and visibility != image.visibility:
                matched = False
            if status is not None and status != image.status:
                matched = False
            if matched:
                results.append(r)
        return results


@Server.filter_registry.register('flavor')
class FlavorFilter(Filter):
    """Filters Servers based on their flavor attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: dns-hostname-enabled
                resource: openstack.server
                filters:
                  - type: flavor
                    flavor_name: m1.tiny
    """
    schema = type_schema(
        'flavor',
        flavor_name={'type': 'string'},
        flavor_id={'type': 'string'},
        vcpus={'type': 'integer'},
        ram={'type': 'integer'},
        swap={'type': 'integer'},
        disk={'type': 'integer'},
        ephemeral={'type': 'integer'},
        is_public={'type': 'boolean'},
    )

    def server_match_flavor(self, server, flavor_name, flavor_id,
                            vcpus, ram, disk, ephemeral, is_public):
        openstack = local_session(self.manager.session_factory).client()
        server_flavor_name = server.flavor.original_name
        flavor = openstack.get_flavor(server_flavor_name)
        if not flavor:
            return False
        if flavor_name and flavor.name != flavor_name:
            return False
        if flavor_id and flavor.id != flavor_id:
            return False
        if vcpus and flavor.vcpus != int(vcpus):
            return False
        if ram and flavor.ram != int(ram):
            return False
        if disk and flavor.disk != int(disk):
            return False
        if ephemeral and flavor.ephemeral != int(ephemeral):
            return False
        if is_public is not None and flavor.is_public != is_public:
            return False
        return True

    def process(self, resources, event=None):
        results = []
        flavor_name = self.data.get('flavor_name', None)
        flavor_id = self.data.get('flavor_id', None)
        vcpus = self.data.get('vcpus', None)
        ram = self.data.get('ram', None)
        disk = self.data.get('disk', None)
        ephemeral = self.data.get('ephemeral', None)
        is_public = self.data.get('is_public', None)
        for server in resources:
            if self.server_match_flavor(server, flavor_name, flavor_id,
                                        vcpus, ram, disk, ephemeral,
                                        is_public):
                results.append(server)
        return results


@Server.filter_registry.register('age')
class AgeFilter(AgeFilter):

    date_attribute = "launched_at"

    schema = type_schema(
        'age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'},
        hours={'type': 'number'},
        minutes={'type': 'number'})

    def get_resource_data(self, i):
        if i.get("launched_at"):
            return i.get("launched_at")
        return i.get("created_at")


@Server.filter_registry.register('tags')
class TagsFilter(Filter):
    """Filters Servers based on their tags

    :example:

    .. code-block:: yaml

            policies:
              - name: demo
                resource: openstack.server
                filters:
                  - type: tags
                    tags:
                    - key: a
                      value: b
    """
    tags_definition = {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'key': {'type': 'string'},
                'value': {'type': 'string'}
            },
            'required': ['key', 'value'],
        }
    }
    schema = type_schema(
        'tags',
        tags=tags_definition,
        op={'type': 'string', 'enum': ['any', 'all']},
    )

    def match_any_tags(self, server, tags):
        for t in tags:
            str_tag = "%s=%s" % (t.get('key'), t.get('value'))
            if str_tag in server.tags:
                return True
        return False

    def match_all_tags(self, server, tags):
        for t in tags:
            str_tag = "%s=%s" % (t.get('key'), t.get('value'))
            if str_tag not in server.tags:
                return False
        return True

    def process(self, resources, event=None):
        results = []
        tags = self.data.get('tags', [])
        op = self.data.get('op', 'all')
        match_fn = {
            'any': self.match_any_tags,
            'all': self.match_all_tags
        }
        for server in resources:
            if match_fn[op](server, tags):
                results.append(server)
        return results


def find_object_by_property(collection, k, v):
    result = []
    for d in collection:
        if hasattr(d, k):
            value = getattr(d, k)
        else:
            value = d.get(k)
        if (v is None and value is None) or value == v:
            result.append(d)
    if not result:
        return None
    assert len(result) == 1
    return result[0]


@Server.filter_registry.register('security-group')
class SecurityGroupFilter(ListItemFilter):
    """Filters Servers based on attached security groups attributes

    :example:

    Finds servers with a security group that is stateful
    .. code-block:: yaml

            policies:
              - name: server-securitygroup-stateful
                resource: openstack.server
                filters:
                  - type: security-group
                    attrs:
                      - type: value
                        key: stateful
                        value: true

    :example:

    Finds servers with a security group that has inbound rules which
    include 0.0.0.0/0 and any port

    .. code-block:: yaml

            policies:
              - name: server-securitygroup-open-to-internet
                resource: openstack.server
                filters:
                  - type: security-group
                    key: security_group_rules
                    attrs:
                      - type: value
                        key: direction
                        value: ingress
                      - type: value
                        key: !port_range_min && !port_range_max
                        value: true
                      - type: value
                        key: remote_ip_prefix
                        value: '0.0.0.0/0'
    """
    schema = type_schema(
        'security-group',
        key={'type': 'string'},
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )

    annotate_items = True
    _client = None

    def get_client(self):
        if self._client:
            return self._client
        self._client = local_session(self.manager.session_factory).client()
        return self._client

    def validate(self):
        self._sg_map = {}
        return super().validate()

    def get_item_values(self, resource):
        result = []
        client = self.get_client()
        sgs_details = client.compute.fetch_server_security_groups(
            resource.get('id')).security_groups
        attached_sgs_ids = [sg_details.get('id') for sg_details in sgs_details]

        for attached_sg_id in attached_sgs_ids:
            if attached_sg_id not in self._sg_map:
                self._sg_map[attached_sg_id] = (
                    client.network.find_security_group(
                        attached_sg_id, ignore_missing=True
                    ).toDict())
            security_group = self._sg_map.get(attached_sg_id)
            if security_group is None:
                continue
            if 'key' in self.data:
                key_values = self.expr.search(security_group)
                result.extend(key_values)
            else:
                result.append(security_group)
        return result


@resources.register('image')
class Image(QueryResourceManager):
    class resource_type(TypeInfo):
        enum_spec = ('list_images', None)
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'status', 'visibility']
