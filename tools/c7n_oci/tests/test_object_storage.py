# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import oci
from pytest_terraform import terraform

from oci_common import OciBaseTest


class TestObjectStorage(OciBaseTest):
    def _get_bucket_details(self, object_storage):
        namespace = object_storage["oci_objectstorage_bucket.test_bucket.namespace"]
        name = object_storage["oci_objectstorage_bucket.test_bucket.name"]
        return namespace, name

    def _fetch_bucket_validation_data(self, resource_manager, namespace_name, bucket_name):
        client = resource_manager.get_client()
        resource = client.get_bucket(namespace_name, bucket_name)
        return oci.util.to_dict(resource.data)

    @terraform("object_storage", scope="class")
    def test_add_defined_tag_to_bucket(self, test, object_storage, with_or_without_compartment):
        """
        test adding defined_tags tag on compute instance
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform("object_storage", scope="class")
    def test_update_bucket(self, test, object_storage, with_or_without_compartment):
        """
        test adding defined_tags tag on compute instance
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform("object_storage", scope="class")
    def test_update_defined_tag_of_bucket(self, test, object_storage):
        """
        test update defined_tags tag on bucket
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "update-defined-tag-to-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [
                    {
                        "type": "update",
                        "defined_tags": self.get_defined_tag("update_tag"),
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

    @terraform("object_storage", scope="class")
    def test_add_freeform_tag_to_bucket(self, test, object_storage):
        """
        test adding freeform tag to bucket
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-tag-to-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("object_storage", scope="class")
    def test_update_freeform_tag_of_bucket(self, test, object_storage):
        """
        test update freeform tag of bucket
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-bucket",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Production"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform("object_storage", scope="class")
    def test_get_freeform_tagged_bucket(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-instance",
                "resource": "oci.bucket",
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

    @terraform("object_storage", scope="class")
    def test_tag_public_bucket(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "tag-public-buckets",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {
                        "type": "attributes",
                        "key": "public_access_type",
                        "value": "ObjectRead",
                        "op": "eq",
                    },
                ],
                "actions": [{"type": "update", "freeform_tags": {"public_access": "true"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["freeform_tags"]["public_access"], "true")

    @terraform("object_storage", scope="class")
    def test_change_public_bucket_to_private(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "change-public-bucket-to-private",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "public_access_type": "NoPublicAccess"}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["public_access_type"], "NoPublicAccess")

    @terraform("object_storage", scope="class")
    def test_update_public_bucket_to_private(self, test, object_storage):
        """
        test get freeform tagged compute instances
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "change-public-bucket-to-private",
                "resource": "oci.bucket",
                "query": [
                    {"namespace_name": namespace_name},
                ],
                "filters": [
                    {"type": "value", "key": "name", "value": bucket_name},
                ],
                "actions": [{"type": "update", "public_access_type": "NoPublicAccess"}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_bucket_validation_data(
            policy.resource_manager, namespace_name, bucket_name
        )
        test.assertEqual(resource["name"], bucket_name)
        test.assertEqual(resource["public_access_type"], "NoPublicAccess")

    @terraform("object_storage", scope="class")
    def test_remove_freeform_tag(self, test, object_storage):
        """
        test remove freeform tag
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "bucket-remove-tag",
                "resource": "oci.bucket",
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

    @terraform("object_storage", scope="class")
    def test_remove_defined_tag(self, test, object_storage):
        """
        test remove defined tag
        """
        namespace_name, bucket_name = self._get_bucket_details(object_storage)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "bucket-remove-tag",
                "resource": "oci.bucket",
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
