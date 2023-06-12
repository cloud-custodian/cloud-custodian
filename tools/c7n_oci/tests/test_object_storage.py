import inspect

import oci
from pytest_terraform import terraform

from oci_common import Module, OciBaseTest, Resource, Scope


class TestObjectStorage(OciBaseTest):
    def _get_bucket_details(self, object_storage):
        compartment_id = object_storage["oci_objectstorage_bucket.test_bucket.compartment_id"]
        namespace = object_storage["oci_objectstorage_bucket.test_bucket.namespace"]
        name = object_storage["oci_objectstorage_bucket.test_bucket.name"]
        return compartment_id, namespace, name

    def _fetch_bucket_validation_data(self, resource_manager, namespace_name, bucket_name):
        client = resource_manager.get_client()
        resource = client.get_bucket(namespace_name, bucket_name)
        return oci.util.to_dict(resource.data)

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_bucket(self, test, object_storage):
        """
        test adding defined_tags tag on compute instance
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-bucket",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update-bucket",
                        "params": {
                            "update_bucket_details": {
                                "defined_tags": self.get_defined_tag("add_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_bucket(self, test, object_storage):
        """
        test update defined_tags tag on bucket
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-defined-tag-to-bucket",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update-bucket",
                        "params": {
                            "update_bucket_details": {
                                "defined_tags": self.get_defined_tag("update_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_bucket(self, test, object_storage):
        """
        test adding freeform tag to bucket
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-tag-to-bucket",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update-bucket",
                        "params": {
                            "update_bucket_details": {
                                "freeform_tags": {"Environment": "Development"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_bucket(self, test, object_storage):
        """
        test update freeform tag of bucket
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-bucket",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update-bucket",
                        "params": {
                            "update_bucket_details": {
                                "freeform_tags": {"Environment": "Production"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_bucket(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-instance",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["name"], bucket_name)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_change_public_bucket_to_private(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "change-public-bucket-to-private",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update-bucket",
                        "params": {
                            "update_bucket_details": {"public_access_type": "NoPublicAccess"}
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["public_access_type"], "NoPublicAccess")

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_remove_freeform_tag(self, test, object_storage):
        """
        test remove freeform tag
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "bucket-remove-tag",
                "resource": Resource.BUCKET.value,
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {"type": "remove-tag", "freeform_tags": ["Project"]},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"].get("Project"), None)

    @terraform(Module.OBJECT_STORAGE.value, scope=Scope.CLASS.value)
    def test_remove_defined_tag(self, test, object_storage):
        """
        test remove defined tag
        """
        compartment_id, namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "bucket-remove-tag",
                "resource": Resource.BUCKET.value,
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "remove-tag",
                        "defined_tags": ["cloud-custodian-test.mark-for-resize"],
                    },
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), None)
