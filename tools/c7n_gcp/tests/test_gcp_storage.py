# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from googleapiclient.errors import HttpError
import pytest
from pytest_terraform import terraform

from gcp_common import BaseTest


class BucketTest(BaseTest):
    def test_bucket_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bucket-query', project_id)
        p = self.load_policy(
            {'name': 'all-buckets', 'resource': 'gcp.bucket'}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], "staging.cloud-custodian.appspot.com")
        self.assertEqual(resources[0]['storageClass'], "STANDARD")

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_bucket_get(self):
        project_id = 'cloud-custodian'
        bucket_name = "staging.cloud-custodian.appspot.com"
        factory = self.replay_flight_data('bucket-get-resource', project_id)
        p = self.load_policy({'name': 'bucket', 'resource': 'gcp.bucket'}, session_factory=factory)
        bucket = p.resource_manager.get_resource(
            {
                "bucket_name": bucket_name,
            }
        )
        self.assertEqual(bucket['name'], bucket_name)
        self.assertEqual(bucket['id'], "staging.cloud-custodian.appspot.com")
        self.assertEqual(bucket['storageClass'], "STANDARD")
        self.assertEqual(bucket['location'], "EU")

        self.assertEqual(
            p.resource_manager.get_urns([bucket]),
            [
                "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
            ],
        )

    def test_enable_uniform_bucket_level_access(self):
        project_id = 'custodian-1291'
        bucket_name = 'c7n-dev-test'
        factory = self.replay_flight_data('bucket-uniform-bucket-access', project_id)
        p = self.load_policy(
            {
                'name': 'bucket',
                'resource': 'gcp.bucket',
                'filters': [
                    {'name': 'c7n-dev-test'},
                    {'iamConfiguration.uniformBucketLevelAccess.enabled': False},
                ],
                'actions': ['set-uniform-access'],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        bucket = p.resource_manager.get_resource(
            {
                "bucket_name": bucket_name,
            }
        )
        self.assertEqual(bucket['name'], bucket_name)
        self.assertEqual(bucket['id'], bucket_name)
        self.assertEqual(bucket['storageClass'], "REGIONAL")
        self.assertEqual(bucket['location'], "US-EAST1")
        self.assertJmes('iamConfiguration.uniformBucketLevelAccess.enabled', bucket, True)

    def test_bucket_iam_policy_filter(self):
        factory = self.replay_flight_data('bucket-iam-policy')
        p = self.load_policy(
            {
                'name': 'bucket',
                'resource': 'gcp.bucket',
                'filters': [
                    {
                        'type': 'iam-policy',
                        'doc': {
                            'key': 'bindings[*].members[]',
                            'op': 'intersect',
                            'value': ['allUsers', 'allAuthenticatedUsers'],
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for resource in resources:
            self.assertTrue('c7n:iamPolicy' in resource)
            bindings = resource['c7n:iamPolicy']['bindings']
            members = set()
            for binding in bindings:
                for member in binding['members']:
                    members.add(member)
            self.assertTrue('allUsers' in members or 'allAuthenticatedUsers' in members)

    def test_bucket_scc_mode(self):
        project_id = "cloud-custodian"
        bucket_name = "staging.cloud-custodian.appspot.com"
        factory = self.replay_flight_data("bucket-get-resource", project_id)
        p = self.load_policy(
            {"name": "bucket", "resource": "gcp.bucket", "mode": {"type": "gcp-scc", "org": 12345}},
            session_factory=factory,
        )
        [bucket] = p.push(
            # Fake a minimal scc finding for a bucket.
            {"finding": {"resourceName": "//storage.googleapis.com/" + bucket_name}, "resource": {}}
        )

        assert bucket["name"] == bucket_name
        assert bucket["id"] == "staging.cloud-custodian.appspot.com"
        assert bucket["storageClass"] == "STANDARD"
        assert bucket["location"] == "EU"

        assert p.resource_manager.get_urns([bucket]) == [
            "gcp:storage::cloud-custodian:bucket/staging.cloud-custodian.appspot.com",
        ]

    @terraform("gcs_bucket")
    def test_bucket_delete(self):
        project_id = "custodian-1291"
        bucket_name = "c7n-bucket-delete-test"
        factory = self.replay_flight_data("bucket-delete", project_id)
        p = self.load_policy(
            {
                "name": "delete-bucket",
                "resource": "gcp.bucket",
                "filters": [{"name": bucket_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(1)

        client = p.resource_manager.get_client()

        with pytest.raises(HttpError):
            client.execute_command("get", {"bucket": bucket_name})
            self.fail("found deleted bucket")
