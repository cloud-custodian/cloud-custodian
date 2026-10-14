# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from c7n.testing import C7N_FUNCTIONAL
from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError
from dateutil import parser
from freezegun import freeze_time
from pytest_terraform import terraform


class SqlInstanceTest(BaseTest):

    def test_sqlinstance_label_params(self):
        p = self.load_policy({
            'name': 'sql-labels',
            'resource': 'gcp.sql-instance'})
        model = p.resource_manager.resource_type
        assert model.get_label_params(
            {'selfLink': 'https://gcp-sql/projects/abc-123/instances/rds-123'},
            {'k': 'v'}) == {
                'project': 'abc-123',
                'instance': 'rds-123',
                'body': {
                    'settings': {
                        'userLabels': {'k': 'v'}
                    }
                }
        }

    def test_sqlinstance_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data('sqlinstance-query', project_id=project_id)
        p = self.load_policy(
            {'name': 'all-sqlinstances',
             'resource': 'gcp.sql-instance'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                f"gcp:sqladmin:us-central1:{project_id}:instance/brenttest-6",
            ],
        )

    def test_sqlinstance_get(self):
        factory = self.replay_flight_data('sqlinstance-get')
        p = self.load_policy(
            {'name': 'one-sqlinstance',
             'resource': 'gcp.sql-instance'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'database_id': 'cloud-custodian:brenttest-2'})
        self.assertEqual(instance['state'], 'RUNNABLE')
        self.assertEqual(
            p.resource_manager.get_urns([instance]),
            [
                "gcp:sqladmin:us-central1:cloud-custodian:instance/brenttest-2",
            ],
        )

    def test_sqlinstance_offhour(self):
        project_id = self.project_id
        factory = self.replay_flight_data("sqlinstance-offhour", project_id=project_id)
        p = self.load_policy(
            {
                "name": "sql-offhour",
                "resource": "gcp.sql-instance",
                "filters": [
                    {
                        "type": "offhour",
                        "default_tz": "utc",
                        "offhour": 18,
                        "tag": "custodian_offhours",
                    }
                ],
            },
            session_factory=factory,
        )
        with freeze_time(parser.parse("2022/09/01 02:15:00")):
            resources = p.run()
            self.assertEqual(len(resources), 1)

    def test_stop_instance(self):
        project_id = self.project_id
        instance_name = 'custodiansqltest'
        factory = self.replay_flight_data('sqlinstance-stop', project_id=project_id)
        p = self.load_policy(
            {'name': 'istop',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': 'custodiansqltest'}],
             'actions': ['stop']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'instance': instance_name})
        self.assertEqual(result['settings']['activationPolicy'], 'NEVER')

    def test_start_instance(self):
        project_id = self.project_id
        instance_name = 'custodiantestsql'
        factory = self.replay_flight_data('sqlinstance-start', project_id=project_id)
        p = self.load_policy(
            {
                'name': 'istart',
                'resource': 'gcp.sql-instance',
                'filters': [
                    {
                        'name': 'custodiantestsql'
                    },
                    {
                        'type': 'value',
                        'key': 'state',
                        'op': 'equal',
                        'value': 'RUNNABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'settings.activationPolicy',
                        'op': 'equal',
                        'value': 'NEVER'
                    }
                ],
                'actions': ['start']
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'instance': instance_name})
        self.assertEqual(result['settings']['activationPolicy'], 'ALWAYS')

    def test_delete_instance(self):
        project_id = self.project_id
        instance_name = 'brenttest-5'
        factory = self.replay_flight_data('sqlinstance-terminate', project_id=project_id)

        p = self.load_policy(
            {'name': 'sqliterm',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': instance_name}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        try:
            result = client.execute_query(
                'get', {'project': project_id,
                        'instance': instance_name})
            self.fail('found deleted instance: %s' % result)
        except HttpError as e:
            self.assertTrue("does not exist" in str(e))

    def test_enable_deletion_instance(self):
        project_id = self.project_id
        instance_name = 'custodiantestsql'
        factory = self.replay_flight_data('sqlinstance-enable-deletion', project_id=project_id)
        p = self.load_policy(
            {
                'name': 'enable-deletion',
                'resource': 'gcp.sql-instance',
                'filters': [
                    {
                        'name': 'custodiantestsql'
                    },
                    {
                        'type': 'value',
                        'key': 'settings.deletionProtectionEnabled',
                        'op': 'equal',
                        'value': False
                    }
                ],
                'actions': [{"type": 'set-deletion-protection', "value": True}]
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'instance': instance_name})
        self.assertEqual(result['settings']['deletionProtectionEnabled'], True)
        p = self.load_policy(
            {
                'name': 'enable-deletion',
                'resource': 'gcp.sql-instance',
                'filters': [
                    {
                        'name': 'custodiantestsql'
                    },
                    {
                        'type': 'value',
                        'key': 'settings.deletionProtectionEnabled',
                        'op': 'equal',
                        'value': True
                    }
                ],
                'actions': [{"type": 'delete', "force": True}]
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_set_high_availability(self):
        project_id = self.project_id
        instance_name = 'custodiantestsql'
        factory = self.replay_flight_data('sqlinstance-high-availability', project_id=project_id)
        p = self.load_policy(
            {
                'name': 'set-high-availability',
                'resource': 'gcp.sql-instance',
                'filters': [
                    {
                        'name': 'custodiantestsql'
                    },
                    {
                        'type': 'value',
                        'key': 'settings.availabilityType',
                        'op': 'equal',
                        'value': 'ZONAL'
                    }
                ],
                'actions': [{"type": 'set-high-availability', "value": True}]
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'instance': instance_name})
        self.assertEqual(result['settings']['availabilityType'], 'REGIONAL')


class SqlUserTest(BaseTest):

    def test_sqluser_query(self):
        project_id = self.project_id
        session_factory = self.replay_flight_data(
            'sqluser-query', project_id=project_id)

        user_name = 'postgres'
        instance_name = 'custodian-postgres'

        filter_annotation_key = 'c7n:sql-instance'
        policy = self.load_policy(
            {'name': 'gcp-sql-user-dryrun',
             'resource': 'gcp.sql-user',
             'filters': [{
                     'type': 'value',
                     'key': '\"{}\".name'.format(filter_annotation_key),
                     'op': 'regex',
                     'value': instance_name}]
             },
            session_factory=session_factory)
        annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        # If fails there, policies using filters for the resource
        # need to be updated since the key has been changed.
        self.assertEqual(annotation_key, filter_annotation_key)

        users = policy.run()

        self.assertEqual(users[0]['name'], user_name)
        self.assertEqual(users[0][annotation_key]['name'], instance_name)
        self.assertEqual(
            policy.resource_manager.get_urns(users),
            [
                f"gcp:sqladmin:us-central1:{project_id}:user/custodian-postgres/postgres",
            ],
        )


class SqlBackupRunTest(BaseTest):

    def test_sqlbackuprun_query(self):
        backup_run_id = '1555592400197'
        instance_name = 'custodian-postgres'
        project_id = self.project_id
        session_factory = self.replay_flight_data('sqlbackuprun-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-sql-backup-run-dryrun',
             'resource': 'gcp.sql-backup-run'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        resources = policy.run()
        backup_run = resources[0]

        self.assertEqual(backup_run['id'], backup_run_id)
        self.assertEqual(backup_run[parent_annotation_key]['name'], instance_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                f"gcp:sqladmin:us-central1:{project_id}:backup-run/custodian-postgres/1555592400197",  # noqa: E501
            ],
        )

    def test_sqlbackuprun_get(self):
        backup_run_id = '1557489381417'
        instance_name = 'custodian-postgres'
        project_id = self.project_id
        session_factory = self.replay_flight_data('sqlbackuprun-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-sql-backup-run-audit',
             'resource': 'gcp.sql-backup-run',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['cloudsql.backupRuns.create']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('sql-backup-create.json')
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['id'], backup_run_id)
        self.assertEqual(resources[0][parent_annotation_key]['name'], instance_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                f"gcp:sqladmin:us-central1:{project_id}:backup-run/custodian-postgres/1557489381417",  # noqa: E501
            ],
        )

    def test_from_insert_time_to_id(self):
        insert_time = '2019-05-10T11:56:21.417Z'
        expected_id = 1557489381417

        session_factory = self.replay_flight_data('sqlbackuprun-get')
        policy = self.load_policy(
            {'name': 'gcp-sql-backup-run-dryrun',
             'resource': 'gcp.sql-backup-run'},
            session_factory=session_factory)
        resource_manager = policy.resource_manager
        actual_id = resource_manager.resource_type._from_insert_time_to_id(insert_time)

        self.assertEqual(actual_id, expected_id)


@terraform('gcp_sql_backup_run_delete')
def test_sql_backup_run_delete(test, gcp_sql_backup_run_delete):
    # When the functional test is run, Terraform will create an instance
    # but backups must be triggered manually before recording. Create at least
    # two backups so the test can verify only the targeted one is deleted:
    #
    #   gcloud sql backups create --instance=<instance_name> --project=<project_id>
    #   gcloud sql backups create --instance=<instance_name> --project=<project_id>
    #
    # Then note the IDs of both backups (visible in the GCP console or via
    # `gcloud sql backups list --instance=<instance_name>`), and set
    # BACKUP_ID_TO_DELETE below to the ID of the one that should be deleted.
    # The other backup must remain untouched after the policy runs.

    project_id = gcp_sql_backup_run_delete['google_sql_database_instance.default.project']
    if C7N_FUNCTIONAL:
        factory = test.record_flight_data(
            'sql-backup-run-delete', project_id=project_id)
    else:
        factory = test.replay_flight_data(
            'sql-backup-run-delete', project_id=project_id)

    instance_name = gcp_sql_backup_run_delete['google_sql_database_instance.default.name']
    client_pre = test.load_policy(
        {'name': 'gcp-sql-backup-run-list', 'resource': 'gcp.sql-backup-run'},
        session_factory=factory,
    ).resource_manager.get_client()
    all_backups = client_pre.execute_query(
        'list', {'project': project_id, 'instance': instance_name})
    all_ids = {r['id'] for r in all_backups.get('items', [])}
    assert len(all_ids) >= 2, (
        "Need at least 2 backups to safely test targeted deletion. "
        "Run: gcloud sql backups create --instance={} --project={}".format(
            instance_name, project_id)
    )

    # Target only the most-recent backup (highest numeric ID) for deletion.
    backup_id_to_delete = str(max(int(i) for i in all_ids))
    surviving_ids_expected = all_ids - {backup_id_to_delete}

    policy = test.load_policy(
        {
            'name': 'gcp-sql-backup-run-delete',
            'resource': 'gcp.sql-backup-run',
            'filters': [
                {
                    'type': 'value',
                    'key': '"c7n:sql-instance".name',
                    'op': 'eq',
                    'value': instance_name,
                },
                {
                    'type': 'value',
                    'key': 'status',
                    'op': 'eq',
                    'value': 'SUCCESSFUL',
                },
                {
                    'type': 'value',
                    'key': 'id',
                    'op': 'eq',
                    'value': backup_id_to_delete,
                },
            ],
            'actions': [{'type': 'delete'}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['id'] == backup_id_to_delete

    if test.recording:
        time.sleep(2)

    client = policy.resource_manager.get_client()
    remaining = client.execute_query(
        'list', {'project': project_id, 'instance': instance_name})
    remaining_ids = {r['id'] for r in remaining.get('items', [])}

    assert backup_id_to_delete not in remaining_ids
    assert surviving_ids_expected.issubset(remaining_ids)


class SqlSslCertTest(BaseTest):

    def test_sqlsslcet_query(self):
        ssl_cert_sha = '62a43e710693b34d5fdb34911a656fd7a3b76cc7'
        instance_name = 'custodian-postgres'
        project_id = self.project_id
        session_factory = self.replay_flight_data('sqlsslcert-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-sql-ssl-cert-dryrun',
             'resource': 'gcp.sql-ssl-cert'},
            session_factory=session_factory)
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        resources = policy.run()
        ssl_cert = resources[0]

        self.assertEqual(ssl_cert['sha1Fingerprint'], ssl_cert_sha)
        self.assertEqual(ssl_cert[parent_annotation_key]['name'], instance_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                f"gcp:sqladmin:us-central1:{project_id}:ssl-cert/custodian-postgres/62a43e710693b34d5fdb34911a656fd7a3b76cc7",  # noqa: E501
            ],
        )

    def test_sqlsslcet_get(self):
        ssl_cert_sha = '49a10ed7135e3171ce5e448cc785bc63b5b81e6c'
        instance_name = 'custodian-postgres'
        project_id = self.project_id
        session_factory = self.replay_flight_data('sqlsslcert-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-sql-ssl-cert-audit',
             'resource': 'gcp.sql-ssl-cert',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['cloudsql.sslCerts.create']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('sql-ssl-cert-create.json')
        parent_annotation_key = policy.resource_manager.resource_type.get_parent_annotation_key()
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['sha1Fingerprint'], ssl_cert_sha)
        self.assertEqual(resources[0][parent_annotation_key]['name'], instance_name)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                f"gcp:sqladmin:us-central1:{project_id}:ssl-cert/custodian-postgres/49a10ed7135e3171ce5e448cc785bc63b5b81e6c",  # noqa: E501
            ],
        )
