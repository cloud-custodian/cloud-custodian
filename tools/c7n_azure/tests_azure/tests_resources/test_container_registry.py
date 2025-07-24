# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template
import datetime
from c7n_azure.resources.container_registry import DeleteImagesAction


class ContainerRegistryTest(BaseTest):
    def setUp(self):
        super(ContainerRegistryTest, self).setUp()

    def test_container_registry_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-container-registry',
                'resource': 'azure.container-registry'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('container_registry.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-container-registry',
            'resource': 'azure.container-registry',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctestcontainerregistry*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('container_registry.json')
    def test_delete_images_action(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - One repo
        - Two images in the repo, one older than the specified days and one newer
        - No keep parameter
        - No match pattern

        Expected outcome:
        - The older image should be deleted
        - The newer image should remain
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff - datetime.timedelta(days=10)  # 10 days before cutoff (deleted)
            date2 = cutoff + datetime.timedelta(days=5)   # 5 days after cutoff   (not deleted)

            if 'list' in args:
                return ['repo1']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]['repository'], 'repo1')
        self.assertEqual(deleted[0]['tag'], 'v2')

    @arm_template('container_registry.json')
    def test_all_images_before_cutoff(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - One repo
        - Two images in the repo, both older than the specified days
        - No keep parameter
        - No match pattern

        Expected outcome:
        - Both images should be deleted
        - No images should remain
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff - datetime.timedelta(days=10)  # 10 days before cutoff (deleted)
            date2 = cutoff - datetime.timedelta(days=5)   # 5 days before cutoff   (deleted)

            if 'list' in args:
                return ['repo1']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 2)
        self.assertEqual(deleted[0]['repository'], 'repo1')
        self.assertEqual(deleted[0]['tag'], 'v1')
        self.assertEqual(deleted[1]['repository'], 'repo1')
        self.assertEqual(deleted[1]['tag'], 'v2')

    @arm_template('container_registry.json')
    def test_no_images_before_cutoff(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - One repo
        - Two images in the repo, both newer than the specified days
        - No keep parameter
        - No match pattern

        Expected outcome:
        - No images should be deleted
        - Both images should remain
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff + datetime.timedelta(days=10)  # 10 days after cutoff (not deleted)
            date2 = cutoff + datetime.timedelta(days=5)   # 5 days after cutoff   (not deleted)

            if 'list' in args:
                return ['repo1']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 0)

    @arm_template('container_registry.json')
    def test_images_exactly_at_cutoff(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - One repo
        - Two images in the repo, one newer than the specified days, one exactly at the cutoff
        - No keep parameter
        - No match pattern

        Expected outcome:
        - The image at the cutoff should not be deleted
        - The newer image should also remain
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff  # Exactly at cutoff (not deleted)
            date2 = cutoff + datetime.timedelta(days=5)   # 5 days after cutoff   (not deleted)

            if 'list' in args:
                return ['repo1']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 0)

    @arm_template('container_registry.json')
    def test_images_before_cutoff_keep_one(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - One repo
        - Two images in the repo, both before the cutoff date
        - Keep parameter set to 1
        - No match pattern

        Expected outcome:
        - One image should be deleted
        - One image should remain due to the keep parameter
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 1
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff - datetime.timedelta(days=10)  # 10 days before cutoff (deleted)
            date2 = cutoff - datetime.timedelta(days=5)   # 5 days before cutoff   (not deleted)

            if 'list' in args:
                return ['repo1']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]['repository'], 'repo1')
        self.assertEqual(deleted[0]['tag'], 'v2')

    @arm_template('container_registry.json')
    def test_basic_pattern(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - Two repos, one matching the pattern and one not
        - Two images in each repo, both before the cutoff date
        - No keep parameter
        - No match pattern

        Expected outcome:
        - Only two images should be deleted overall, since one repo does not match the pattern
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0,
                    'match': 'repo1'
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff - datetime.timedelta(days=10)  # 10 days before cutoff
            date2 = cutoff - datetime.timedelta(days=5)   # 5 days before cutoff

            if 'list' in args:
                return ['repo1', 'repo2']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 2)
        self.assertEqual(deleted[0]['repository'], 'repo1')
        self.assertEqual(deleted[0]['tag'], 'v1')
        self.assertEqual(deleted[1]['repository'], 'repo1')
        self.assertEqual(deleted[1]['tag'], 'v2')

    @arm_template('container_registry.json')
    def test_regex_pattern(self):
        """
        Test the delete-images action in the Azure Container Registry given:
        - Three repos, two matching the regex pattern and one not
        - Two images in each repo, both before the cutoff date
        - No keep parameter
        - No match pattern

        Expected outcome:
        - Only four images should be deleted overall, since one repo does not match the pattern
        """
        DAYS = 30

        p = self.load_policy({
            'name': 'test-delete-images',
            'resource': 'azure.container-registry',
            'actions': [
                {
                    'type': 'delete-images',
                    'days': DAYS,
                    'keep': 0,
                    'match': 'test-.*'
                }
            ]
        }, validate=True)

        def mock_az_cli(self, args, expect_json=False):
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(days=DAYS)

            date1 = cutoff - datetime.timedelta(days=10)  # 10 days before cutoff
            date2 = cutoff - datetime.timedelta(days=5)   # 5 days before cutoff

            if 'list' in args:
                return ['test-repo1', 'test-repo2', 'other-repo']
            elif 'show-manifests' in args:
                return [
                    {
                        'tags': ['v1'],
                        'digest': 'sha256:abcd1234',
                        'timestamp': date2.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    },
                    {
                        'tags': ['v2'],
                        'digest': 'sha256:efgh5678',
                        'timestamp': date1.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                ]
            else:
                return {}  # no-op

        DeleteImagesAction._az_cli = mock_az_cli

        resources = p.run()

        deleted = resources[0].get('c7n:deleted-images', [])
        self.assertEqual(len(deleted), 4)
        self.assertEqual(deleted[0]['repository'], 'test-repo1')
        self.assertEqual(deleted[0]['tag'], 'v1')
        self.assertEqual(deleted[1]['repository'], 'test-repo1')
        self.assertEqual(deleted[1]['tag'], 'v2')
        self.assertEqual(deleted[2]['repository'], 'test-repo2')
        self.assertEqual(deleted[2]['tag'], 'v1')
        self.assertEqual(deleted[3]['repository'], 'test-repo2')
        self.assertEqual(deleted[3]['tag'], 'v2')
