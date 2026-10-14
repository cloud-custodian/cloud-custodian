# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.exceptions import PolicyValidationError
from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project
from gcp_common import BaseTest
from pytest_terraform import terraform


# DATABASE TESTS
@terraform("firestore_database")
def test_firestore_database_query(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-database-query", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-database-query", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-database-query",
            "resource": "gcp.firestore-database",
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 2)


@terraform("firestore_database")
def test_firestore_database_filter_by_location(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-database-filter-location", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-database-filter-location", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-database-filter-location",
            "resource": "gcp.firestore-database",
            "filters": [{"type": "value", "key": "locationId", "value": "us-east1"}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["locationId"], "us-east1")


@terraform("firestore_database")
def test_firestore_database_get(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-database-get", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-database-get", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-database-get",
            "resource": "gcp.firestore-database",
        },
        session_factory=session_factory,
    )

    listed = policy.run()
    test.assertTrue(len(listed) > 0)

    db = policy.resource_manager.get_resource({"resourceName": listed[0]["name"]})
    test.assertEqual(db["name"], listed[0]["name"])


# BACKUP SCHEDULE TESTS
@terraform("firestore_database")
def test_firestore_backup_schedule_query(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-backup-schedule-query", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-backup-schedule-query", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-backup-schedule-query",
            "resource": "gcp.firestore-backup-schedule",
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 2)
    test.assertTrue(all("/backupSchedules/" in r["name"] for r in resources))


@terraform("firestore_database")
def test_firestore_backup_schedule_filter(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-backup-schedule-filter", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-backup-schedule-filter", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-backup-schedule-filter",
            "resource": "gcp.firestore-backup-schedule",
            "filters": [{"type": "value", "key": "retention", "value": "604800s"}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["retention"], "604800s")


@terraform("firestore_database")
def test_firestore_backup_schedule_get(test, firestore_database):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-backup-schedule-get", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-backup-schedule-get", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-backup-schedule-get",
            "resource": "gcp.firestore-backup-schedule",
        },
        session_factory=session_factory,
    )

    listed = policy.run()
    test.assertTrue(len(listed) > 0)

    schedule = policy.resource_manager.get_resource({"resourceName": listed[0]["name"]})
    test.assertEqual(schedule["name"], listed[0]["name"])
    test.assertTrue("c7n:firestore-database" in schedule)


# FIELDS TESTS
# Functional tests take ~10 minutes to run
@terraform("firestore_fields")
def test_firestore_field_query(test, firestore_fields):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-field-query", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-field-query", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-field-query",
            "resource": "gcp.firestore-field",
            "query": [{"collectionId": "orders", "filter": "ttlConfig:*"}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 2)
    test.assertTrue(
        all("/collectionGroups/orders/fields/expireAt" in r["name"] for r in resources)
    )


@terraform("firestore_fields")
def test_firestore_field_filter_name(test, firestore_fields):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-field-filter-name", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-field-filter-name", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-field-filter-name",
            "resource": "gcp.firestore-field",
            "query": [{"collectionId": "orders", "filter": "ttlConfig:*"}],
            "filters": [
                {
                    "type": "value",
                    "key": "name",
                    "op": "regex",
                    "value": ".*/databases/.+-east/collectionGroups/orders/fields/expireAt$",
                }
            ],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)


@terraform("firestore_fields")
def test_firestore_field_get(test, firestore_fields):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-field-get", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-field-get", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-field-get",
            "resource": "gcp.firestore-field",
            "query": [{"collectionId": "orders", "filter": "ttlConfig:*"}],
        },
        session_factory=session_factory,
    )

    listed = policy.run()
    test.assertTrue(len(listed) > 0)

    field = policy.resource_manager.get_resource({"resourceName": listed[0]["name"]})
    test.assertEqual(field["name"], listed[0]["name"])
    test.assertTrue("c7n:firestore-database" in field)


# INDEX TESTS
# Functional test take ~5-6 minutes to run
@terraform("firestore_indexes")
def test_firestore_index_query(test, firestore_indexes):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-index-query", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-index-query", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-index-query",
            "resource": "gcp.firestore-index",
            "query": [{"collectionId": "orders"}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 2)


@terraform("firestore_indexes")
def test_firestore_index_filter_query_scope(test, firestore_indexes):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-index-filter-query-scope", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-index-filter-query-scope", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-index-filter-query-scope",
            "resource": "gcp.firestore-index",
            "query": [{"collectionId": "orders"}],
            "filters": [
                {
                    "type": "value",
                    "key": "queryScope",
                    "value": "COLLECTION_GROUP",
                }
            ],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["queryScope"], "COLLECTION_GROUP")


@terraform("firestore_indexes")
def test_firestore_index_get(test, firestore_indexes):
    project_id = get_default_project()

    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            "firestore-index-get", project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data(
            "firestore-index-get", project_id=project_id
        )

    policy = test.load_policy(
        {
            "name": "firestore-index-get",
            "resource": "gcp.firestore-index",
            "query": [{"collectionId": "orders"}],
        },
        session_factory=session_factory,
    )

    listed = policy.run()
    test.assertTrue(len(listed) > 0)

    index = policy.resource_manager.get_resource({"resourceName": listed[0]["name"]})
    test.assertEqual(index["name"], listed[0]["name"])
    test.assertTrue("c7n:firestore-database" in index)


class FirestoreValidationTest(BaseTest):
    def test_firestore_field_requires_collection_id(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "firestore-field-requires-collection-id",
                    "resource": "gcp.firestore-field",
                }
            )

    def test_firestore_index_requires_collection_id(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "firestore-index-requires-collection-id",
                    "resource": "gcp.firestore-index",
                }
            )
