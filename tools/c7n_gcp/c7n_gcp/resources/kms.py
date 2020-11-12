# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re

from c7n.utils import local_session
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo, \
    GcpLocation


@resources.register('kms-keyring')
class KmsKeyRing(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudkms'
        version = 'v1'
        component = 'projects.locations.keyRings'
        enum_spec = ('list', 'keyRings[]', None)
        scope = None
        name = id = 'name'
        default_report_fields = [
            "name", "createTime"]
        asset_type = "cloudkms.googleapis.com/KeyRing"

        @staticmethod
        def get(client, resource_info):
            name = 'projects/{}/locations/{}/keyRings/{}' \
                .format(resource_info['project_id'],
                        resource_info['location'],
                        resource_info['key_ring_id'])
            return client.execute_command('get', {'name': name})

    def get_resource_query(self):
        if 'query' in self.data:
            for child in self.data.get('query'):
                if 'location' in child:
                    location_query = child['location']
                    return {'parent': location_query if isinstance(
                        location_query, list) else [location_query]}

    def _fetch_resources(self, query):
        super_fetch_resources = QueryResourceManager._fetch_resources
        session = local_session(self.session_factory)
        project = session.get_default_project()
        locations = (query['parent'] if query and 'parent' in query
                     else GcpLocation.get_service_locations('kms'))
        project_locations = ['projects/{}/locations/{}'.format(project, location)
                             for location in locations]
        key_rings = []
        for location in project_locations:
            key_rings.extend(super_fetch_resources(self, {'parent': location}))
        return key_rings


@resources.register('kms-cryptokey')
class KmsCryptoKey(ChildResourceManager):
    """GCP Resource
    https://cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys
    """
    def _get_parent_resource_info(self, child_instance):
        project_id, location, key_ring_id = re.match(
            'projects/(.*?)/locations/(.*?)/keyRings/(.*?)/cryptoKeys/.*',
            child_instance['name']).groups()
        return {'project_id': project_id,
                'location': location,
                'key_ring_id': key_ring_id}

    def get_resource_query(self):
        """Does nothing as self does not need query values unlike its parent
        which receives them with the use_child_query flag."""
        pass

    class resource_type(ChildTypeInfo):
        service = 'cloudkms'
        version = 'v1'
        component = 'projects.locations.keyRings.cryptoKeys'
        enum_spec = ('list', 'cryptoKeys[]', None)
        scope = None
        name = id = 'name'
        default_report_fields = [
            name, "purpose", "createTime", "nextRotationTime", "rotationPeriod"]
        parent_spec = {
            'resource': 'kms-keyring',
            'child_enum_params': [
                ('name', 'parent')
            ],
            'use_child_query': True
        }
        asset_type = "cloudkms.googleapis.com/CryptoKey"

        @staticmethod
        def get(client, resource_info):
            name = 'projects/{}/locations/{}/keyRings/{}/cryptoKeys/{}' \
                .format(resource_info['project_id'],
                        resource_info['location'],
                        resource_info['key_ring_id'],
                        resource_info['crypto_key_id'])
            return client.execute_command('get', {'name': name})


@resources.register('kms-cryptokey-version')
class KmsCryptoKeyVersion(ChildResourceManager):
    """GCP Resource
    https://cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys.cryptoKeyVersions
    """
    def _get_parent_resource_info(self, child_instance):
        path = 'projects/(.*?)/locations/(.*?)/keyRings/(.*?)/cryptoKeys/(.*?)/cryptoKeyVersions/.*'
        project_id, location, key_ring_id, crypto_key_id = \
            re.match(path, child_instance['name']).groups()
        return {'project_id': project_id,
                'location': location,
                'key_ring_id': key_ring_id,
                'crypto_key_id': crypto_key_id}

    def get_resource_query(self):
        """Does nothing as self does not need query values unlike its parent
        which receives them with the use_child_query flag."""
        pass

    class resource_type(ChildTypeInfo):
        service = 'cloudkms'
        version = 'v1'
        component = 'projects.locations.keyRings.cryptoKeys.cryptoKeyVersions'
        enum_spec = ('list', 'cryptoKeyVersions[]', None)
        scope = None
        name = id = 'name'
        default_report_fields = [
            "name", "state", "protectionLevel", "algorithm", "createTime", "destroyTime"]
        parent_spec = {
            'resource': 'kms-cryptokey',
            'child_enum_params': [
                ('name', 'parent')
            ],
            'use_child_query': True
        }
        asset_type = "cloudkms.googleapis.com/CryptoKeyVersion"

        @staticmethod
        def get(client, resource_info):
            name = 'projects/{}/locations/{}/keyRings/{}/cryptoKeys/{}/cryptoKeyVersions/{}'\
                .format(resource_info['project_id'],
                        resource_info['location'],
                        resource_info['key_ring_id'],
                        resource_info['crypto_key_id'],
                        resource_info['crypto_key_version_id'])
            return client.execute_command('get', {'name': name})
