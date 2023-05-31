import inspect

from oci_common import Module, OciBaseTest, Resource, Scope
from pytest_terraform import terraform


class TestCompute(OciBaseTest):

    def _get_instance_details(self, instance):
        compartment_id  = instance['oci_core_instance.test_instance.compartment_id']
        ocid = instance['oci_core_instance.test_instance.id']
        name = instance['oci_core_instance.test_instance.display_name']
        return compartment_id, ocid, name
    
    def _get_instance_params(self, name):
        return {'display_name':name}

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_instance(self, test, compute):
        '''
        test adding defined_tags tag on compute instance
        '''
        compartment_id, ocid, name = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'add-defined-tag-to-instance',
                'resource': Resource.COMPUTE.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id}
                    },
                    {
                        'type': 'value',
                        'key': 'identifier',
                        'value': ocid
                    }
                ],
                'actions': [
                    {
                        'type': 'update_instance',
                        'params': {'update_instance_details':{'defined_tags':self.get_defined_tag('add_tag')}}
                    }
                ]
            },
            session_factory=session_factory
        )
        self.wait_for_resource_search_sync()
        policy.run()
        resources = self.get_resources(policy, compartment_id, id = ocid, **self._get_instance_params(name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['id'], ocid)
        test.assertEqual(self.get_defined_tag_value(resources[0]['defined_tags']), 'true')
    
    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_instance(self, test, compute):
        '''
        test update defined_tags tag on compute instance
        '''
        compartment_id, ocid, name = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        compartment_id = compute['oci_core_instance.test_instance.compartment_id']
        ocid = compute['oci_core_instance.test_instance.id']

        policy = test.load_policy(
            {
                'name': 'update-defined-tag-from-instance',
                'resource': Resource.COMPUTE.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id}
                    },
                    {
                        'type': 'value',
                        'key': 'identifier',
                        'value': ocid
                    }
                ],
                'actions': [
                    {
                        'type': 'update_instance',
                        'params': {'update_instance_details':{'defined_tags':self.get_defined_tag('update_tag')}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, id = ocid, **self._get_instance_params(name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['id'], ocid)
        test.assertEqual(self.get_defined_tag_value(resources[0]['defined_tags']), 'false')
    
    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_instance(self, test, compute):
        '''
        test adding freeform tag on compute instance
        '''
        compartment_id, ocid, name = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'add-freeform-tag-to-instance',
                'resource': Resource.COMPUTE.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id}
                    },
                    {
                        'type': 'value',
                        'key': 'identifier',
                        'value': ocid
                    }
                ],
                'actions': [
                    {
                        'type': 'update_instance',
                        'params': {'update_instance_details':{'freeform_tags':{'Environment':'Development'}}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, id = ocid, **self._get_instance_params(name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['id'], ocid)
        test.assertEqual(resources[0]['freeform_tags']['Environment'], 'Development')
    
    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_instance(self, test, compute):
        '''
        test update freeform tag on compute instance
        '''
        compartment_id, ocid, name = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'update-freeform-tag-from-instance',
                'resource': Resource.COMPUTE.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id}
                    },
                    {
                        'type': 'value',
                        'key': 'identifier',
                        'value': ocid
                    }
                ],
                'actions': [
                    {
                        'type': 'update_instance',
                        'params': {'update_instance_details':{'freeform_tags':{'Environment':'Production'}}}
                    }
                ]
            },
            session_factory=session_factory
        )
        policy.run()
        resources = self.get_resources(policy, compartment_id, id = ocid, **self._get_instance_params(name))
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['id'], ocid)
        test.assertEqual(resources[0]['freeform_tags']['Environment'], 'Production')
        
    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_instance(self, test, compute):
        '''
        test get freeform tagged compute instances
        '''
        compartment_id, ocid, _ = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(self.__class__.__name__, inspect.currentframe().f_code.co_name)
        policy = test.load_policy(
            {
                'name': 'get-tagged-instance',
                'resource': Resource.COMPUTE.value,
                'filters': [
                    {
                        'type': 'query',
                        'params': {'compartment_id':compartment_id}
                    },
                    {
                        'type': 'value',
                        'key': 'freeform_tags.Project',
                        'value': 'CNCF'
                    },
                    {
                        'type': 'value',
                        'key': 'identifier',
                        'value': ocid
                    }   
                ]
            },
            session_factory=session_factory
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]['identifier'], ocid)
        test.assertEqual(resources[0]['freeform_tags']['Project'], 'CNCF')