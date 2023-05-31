import inspect

from oci_common import Module, OciBaseTest, Resource, Scope
from pytest_terraform import terraform


class TestObjectStorage(OciBaseTest):

    def _get_bucket_details(self, object_storage):
        compartment_id  = object_storage['oci_objectstorage_bucket.test_bucket.compartment_id']
        namespace = object_storage['oci_objectstorage_bucket.test_bucket.namespace']
        name = object_storage['oci_objectstorage_bucket.test_bucket.name']
        return compartment_id, namespace, name
    
    def _get_bucket_params(self, namespace_name):
        return {'namespace_name':namespace_name, 'fields': ['tags']}

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_bucket(self, test, object_storage):
        '''
        test adding defined_tags tag on compute instance
        '''
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'add-defined-tag-to-bucket',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id
                        }
                    },
                    {
                        'type': 'value',
                        'key': 'display_name',
                        'value': bucket_name
                    }
                ],
                'actions': [
                    {
                        'type': 'update_bucket',
                        'params': {'update_bucket_details':{'defined_tags':self.get_defined_tag('add_tag')}}
                    }
                ]
            },
            session_factory=session_factory
        )
        self.wait_for_resource_search_sync()
        policy.run()
        resources = self.get_resources(policy, compartment_id, name=bucket_name, **self._get_bucket_params(namespace_name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['name'], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resources[0]['defined_tags']), 'true')
    
    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_bucket(self, test, object_storage):
        '''
        test update defined_tags tag on bucket
        '''
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'update-defined-tag-to-bucket',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id
                        }
                    },
                    {
                        'type': 'value',
                        'key': 'display_name',
                        'value': bucket_name
                    }
                ],
                'actions': [
                    {
                        'type': 'update_bucket',
                        'params': {'update_bucket_details':{'defined_tags':self.get_defined_tag('update_tag')}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, name=bucket_name, **self._get_bucket_params(namespace_name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['name'], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resources[0]['defined_tags']), 'false')
    
    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_bucket(self, test, object_storage):
        '''
        test adding freeform tag to bucket
        '''
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'add-tag-to-bucket',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id
                        }
                    },
                    {
                        'type': 'value',
                        'key': 'display_name',
                        'value': bucket_name
                    }
                ],
                'actions': [
                    {
                        'type': 'update_bucket',
                        'params': {'update_bucket_details':{'freeform_tags':{'Environment':'Development'}}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, name=bucket_name, **self._get_bucket_params(namespace_name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['name'], bucket_name)
        test.assertEqual(resources[0]['freeform_tags']['Environment'], 'Development')
    
    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_bucket(self, test, object_storage):
        '''
        test update freeform tag of bucket
        '''
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'update-freeform-tag-of-bucket',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id
                        }
                    },
                    {
                        'type': 'value',
                        'key': 'display_name',
                        'value': bucket_name
                    }
                ],
                'actions': [
                    {
                        'type': 'update_bucket',
                        'params': {'update_bucket_details':{'freeform_tags':{'Environment':'Production'}}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, name=bucket_name, **self._get_bucket_params(namespace_name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['name'], bucket_name)
        test.assertEqual(resources[0]['freeform_tags']['Environment'], 'Production')
    
    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_bucket(self, test, object_storage):
        '''
        test get freeform tagged compute instances
        '''
        compartment_id, _, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'get-freeform-tagged-instance',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id,
                        }
                    },
                     {
                        'type': 'value',
                        'key': 'freeform_tags.Project',
                        'value': 'CNCF'
                    } 
                ]
            },
            session_factory=session_factory
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['display_name'], bucket_name)
        test.assertEqual(resources[0]['freeform_tags']['Project'], 'CNCF')

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_change_public_bucket_to_private(self, test, object_storage):
        '''
        test get freeform tagged compute instances
        '''
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'change-public-bucket-to-private',
                'resource': Resource.BUCKET.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id
                        }
                    },
                     {
                        'type': 'value',
                        'key': 'display_name',
                        'value': bucket_name
                    }
                ],
                'actions': [
                    {
                        'type': 'update_bucket',
                        'params': {'update_bucket_details':{'public_access_type':'NoPublicAccess'}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, name=bucket_name, **self._get_bucket_params(namespace_name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['name'], bucket_name)
        #TODO: As of now there is no policy/method to get the public access type
        #test.assertEqual(resources[0]['public_access_type'], 'NoPublicAccess')
    

