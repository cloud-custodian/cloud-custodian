# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import logging
from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser, ThreadHelper
from unittest.mock import patch, MagicMock
import pytest
from ..azure_common import (
    DEFAULT_SUBSCRIPTION_ID, BaseTest, arm_template, cassette_name, requires_arm_polling,
    strict_cassette
)
from azure.core.exceptions import AzureError, HttpResponseError
from c7n_azure.resources.disk import DiskSnapshotAction, ModifyDiskTypeAction
from azure.mgmt.compute import ComputeManagementClient


class DiskTest(BaseTest):
    def setUp(self):
        super(DiskTest, self).setUp()

    def test_azure_disk_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-disk',
                'resource': 'azure.disk'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('disk.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-disk',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestvm_OsDisk_1_81338ced63fa4855b8a5f3e2bab5213c'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class ModifyDiskTypeTests(BaseTest):
    """Test class for modifying disk types (SKU) of Azure disks."""

    def setUp(self, *args, **kwargs):
        super(ModifyDiskTypeTests, self).setUp(*args, **kwargs)
        self.mock_client = MagicMock(spec=ComputeManagementClient)  # Ensure correct spec
        self.manager = MagicMock()
        self.manager.get_client.return_value = self.mock_client

        # Correctly configure a logger
        self.manager.log = logging.getLogger("ModifyDiskTypeTestLogger")

        self.action = ModifyDiskTypeAction(
            data={'new_sku': 'Standard_LRS', 'retries': 3, 'delay': 5}, manager=self.manager
        )
        self.action.client = self.mock_client
        self.action.MAX_VM_WAIT_TIME = 5  # Reduce wait time for testing
        self.action.VM_CHECK_INTERVAL = 1  # Reduce sleep time for testing

        self.client = local_session(Session).client('azure.mgmt.compute.ComputeManagementClient')

    def tearDown(self, *args, **kwargs):
        super(ModifyDiskTypeTests, self).tearDown(*args, **kwargs)

    def _fetch_disk(self, disk_id):
        """
        Fetch disk details using Azure SDK.
        :param disk_id: The full resource ID of the disk.
        :return: Disk resource object.
        """
        resource_group, disk_name = self._extract_resource_group_and_name(disk_id)
        return self.client.disks.get(resource_group, disk_name)

    def _extract_resource_group_and_name(self, resource_id):
        """
        Extracts the resource group and resource name from a given Azure resource ID.
        Uses the standardized ResourceIdParser for consistency across the project.
        """
        resource_group = ResourceIdParser.get_resource_group(resource_id)
        resource_name = ResourceIdParser.get_resource_name(resource_id)
        return resource_group, resource_name

    # --- TESTING new Action--- ###

    @pytest.mark.vcr(record_mode='all')
    @arm_template('disk_type_modify.json')
    @cassette_name('change_sku_unattached_disks')
    def test_change_sku_unattached_disks(self):
        """Test to validate unattached disk SKU change"""
        policy = self.load_policy(
            {
                'name': 'change-unattached-disk-type',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'properties.diskState',
                        'op': 'eq',
                        'value': 'Unattached',
                    },
                    {
                        'type': 'value',
                        'key': "id",
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            },
            validate=True
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')

    @pytest.mark.vcr(record_mode='all')
    @arm_template('disk_type_modify.json')
    @cassette_name('change-attached-disk-type')
    def test_change_sku_attached_disks(self):
        """Test to validate attached disk SKU change"""
        policy = self.load_policy(
            {
                'name': 'change-attached-disk-type',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'properties.diskState',
                        'op': 'eq',
                        'value': 'Attached',
                    },
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    }
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            },
            validate=True
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')
            self.assertIsNotNone(disk.last_ownership_update_time)

    @pytest.mark.vcr(record_mode='all')
    @arm_template('disk_type_modify.json')
    @cassette_name('no-change-for-correct-type')
    def test_no_change_for_correct_sku(self):
        """Test to validate no change for disks with correct SKU"""
        policy = self.load_policy(
            {
                'name': 'no-change-for-correct-type',
                'resource': 'azure.disk',
                'filters': [
                    {'type': 'value', 'key': 'sku.name', 'op': 'eq', 'value': 'Standard_LRS'},
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            },
            validate=True
        )

        resources = policy.run()
        self.assertEqual(len(resources), 3)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')

    @pytest.mark.vcr(record_mode='all')
    @arm_template('disk_type_modify.json')
    @cassette_name('skip-unsupported-disk-state')
    def test_skip_unsupported_disk_state(self):
        """Test to validate skipping of unsupported disk states"""
        policy = self.load_policy(
            {
                'name': 'skip-unsupported-disk-state',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'sku.name',
                        'op': 'eq',
                        'value': 'ActiveSAS',
                    },
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            },
            validate=True
        )

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    # --- TESTING _assess_vm_state() --- ###

    def test_assess_vm_state(self):
        """Test multiple cases of _assess_vm_state using a loop."""
        forbidden_states = ["Updating", "Creating", "Deleting", "Failed", "Canceled"]
        test_cases = [
            # Forbidden provisioning states (all should return can_proceed=False)
            *[
                (
                    state,
                    [],
                    {
                        'can_proceed': False,
                        'should_deallocate': False,
                        'reason': f"Provisioning state '{state}'",
                    },
                )
                for state in forbidden_states
            ],
            # VM already deallocated
            (
                "Succeeded",
                ["PowerState/deallocated"],
                {
                    'can_proceed': True,
                    'should_deallocate': False,
                    'reason': "VM is already deallocated",
                },
            ),
            # VM running/stopped requiring deallocation
            (
                "Succeeded",
                ["PowerState/running"],
                {
                    'can_proceed': True,
                    'should_deallocate': True,
                    'reason': "Power state 'Running', will deallocate and update",
                },
            ),
            (
                "Succeeded",
                ["PowerState/stopped"],
                {
                    'can_proceed': True,
                    'should_deallocate': True,
                    'reason': "Power state 'Stopped', will deallocate and update",
                },
            ),
            # VM unknown or transitional state
            (
                "Succeeded",
                ["PowerState/starting"],
                {
                    'can_proceed': False,
                    'should_deallocate': False,
                    'reason': "Power state 'Starting' is transitional or unknown",
                },
            ),
            (
                "Succeeded",
                [],
                {
                    'can_proceed': False,
                    'should_deallocate': False,
                    'reason': "Power state 'Unknown' is transitional or unknown",
                },
            ),
            (
                "Succeeded",
                ["OtherState/something_else"],
                {
                    'can_proceed': False,
                    'should_deallocate': False,
                    'reason': "Power state 'Unknown' is transitional or unknown",
                },
            ),
        ]

        for provisioning_state, power_statuses, expected_result in test_cases:
            with self.subTest(provisioning_state=provisioning_state, power_statuses=power_statuses):
                vm = MagicMock(provisioning_state=provisioning_state)
                vm.instance_view = (
                    MagicMock(statuses=[MagicMock(code=code) for code in power_statuses])
                    if power_statuses
                    else None
                )
                result = self.action._assess_vm_state(vm)
                print(f"Test Case: Provisioning={provisioning_state}, Power={power_statuses}")
                print(f"Expected: {expected_result}")
                print(f"Returned: {result}\n")
                self.assertEqual(result, expected_result)

    # --- TESTING super() --- ###

    @patch.object(ModifyDiskTypeAction, '_process_resource', return_value="Processed Resource")
    def test_process_resource_calls_super(self, mock_super_process):
        """Test that _process_resource correctly calls and returns the super method."""
        resource = {'name': 'test-disk'}

        result = self.action._process_resource(resource)

        # Ensure the parent method was called
        mock_super_process.assert_called_once_with(resource)
        # Ensure the return value is properly forwarded
        self.assertEqual(result, "Processed Resource")

    @patch.object(
        ModifyDiskTypeAction, '_process_resource', side_effect=Exception("Mock Exception")
    )
    def test_process_resource_handles_exception(self, mock_super_process):
        """Test that _process_resource handles exceptions from the parent method."""
        resource = {'name': 'test-disk'}

        with self.assertRaises(Exception) as context:
            self.action._process_resource(resource)

        # Ensure the parent method was called
        mock_super_process.assert_called_once_with(resource)
        # Ensure the exception was raised correctly
        self.assertEqual(str(context.exception), "Mock Exception")

    # --- TESTING validate() --- ###

    def test_validate_invalid_sku(self):
        """Test that validate() raises an error for an invalid SKU."""
        action = ModifyDiskTypeAction(
            data={'new_sku': 'Invalid_Sku', 'retries': 2, 'delay': 1}, manager=self.manager
        )
        with self.assertRaises(ValueError):
            action.validate()

    def test_validate_invalid_retries(self):
        """Test that validate() raises an error for invalid retries."""
        action = ModifyDiskTypeAction(
            data={'new_sku': 'Standard_LRS', 'retries': -1, 'delay': 1}, manager=self.manager
        )
        with self.assertRaises(ValueError):
            action.validate()

    def test_validate_invalid_delay(self):
        """Test that validate() raises an error for invalid delay."""
        action = ModifyDiskTypeAction(
            data={'new_sku': 'Standard_LRS', 'retries': 2, 'delay': 0}, manager=self.manager
        )
        with self.assertRaises(ValueError):
            action.validate()

    # --- TESTING update_disk_sku_with_retries() --- ###

    @patch.object(ComputeManagementClient, 'disks', new_callable=MagicMock)
    def test_update_disk_sku_api_failure_azure_error(self, mock_disks):
        """Test that update_disk_sku retries on API failure
        and logs the error when an AzureError occurs."""

        self.action.client.disks.begin_update.side_effect = AzureError("Mock API Failure")

        disk = {
            'id': '/subscriptions/test/resourceGroups/rg/providers/\
            Microsoft.Compute/disks/test-disk',
            'name': 'test-disk',
            'sku': {'name': 'Premium_LRS'},
            'location': 'eastus',
        }

        with self.assertLogs(self.action.manager.log, level='ERROR') as cm:
            with self.assertRaises(RuntimeError):  # Ensure it raises an error after retries
                self.action.update_disk_sku_with_retries(disk)

        # Debugging output
        print("\n".join(cm.output))

        # Ensure correct log message appears
        self.assertTrue(
            any("AzureError on attempt" in log for log in cm.output),
            f"Expected 'AzureError on attempt' in logs but got: {cm.output}",
        )

        # Ensure retries occurred
        self.assertEqual(self.action.client.disks.begin_update.call_count, self.action.retries)

    @patch.object(ComputeManagementClient, 'disks', new_callable=MagicMock)
    def test_update_disk_sku_api_failure_generic_exception(self, mock_disks):
        """Test that update_disk_sku retries and logs the error when a generic Exception occurs."""

        self.action.client.disks.begin_update.side_effect = Exception("Unexpected Error")
        disk = {
            'id': '/subscriptions/test/resourceGroups/rg/\
            providers/Microsoft.Compute/disks/test-disk',
            'name': 'test-disk',
            'sku': {'name': 'Premium_LRS'},
            'location': 'eastus',
        }

        with self.assertLogs(self.action.manager.log, level='ERROR') as cm:
            with self.assertRaises(RuntimeError):  # Ensure it raises an error after retries
                self.action.update_disk_sku_with_retries(disk)

        # Debugging output
        print("\n".join(cm.output))

        # Ensure correct log message appears
        self.assertTrue(
            any("Attempt" in log and "failed for disk" in log for log in cm.output),
            f"Expected 'Attempt X failed for disk' in logs but got: {cm.output}",
        )

        # Ensure retries occurred
        self.assertEqual(self.action.client.disks.begin_update.call_count, self.action.retries)

    # --- TESTING VM OPERATIONS --- ###

    @patch.object(ComputeManagementClient, 'virtual_machines', new_callable=MagicMock)
    def test_deallocate_vm_api_failure(self, mock_vm):
        """Test that VM deallocate logs an error when the API call fails."""

        self.action.client.virtual_machines.begin_deallocate.side_effect = AzureError(
            "Deallocate Failure"
        )

        with self.assertLogs(self.action.manager.log, level='ERROR') as cm:
            with self.assertRaises(AzureError):
                self.action.deallocate_vm("rg", "vm-name")

        # Debugging output
        print("\n".join(cm.output))

        # Ensure correct log message appears
        self.assertTrue(
            any("Azure API error deallocating VM" in log for log in cm.output),
            f"Expected 'Azure API error deallocating VM' in logs but got: {cm.output}",
        )

        # Ensure the deallocate method was called
        self.action.client.virtual_machines.begin_deallocate.assert_called_once_with(
            "rg", "vm-name"
        )

    @patch.object(ComputeManagementClient, 'virtual_machines', new_callable=MagicMock)
    def test_restart_vm_generic_failure(self, mock_vm):
        """Test that VM restart logs unexpected error and raises."""
        self.action.client.virtual_machines.begin_start.side_effect = Exception(
            "Unexpected Failure"
        )

        with self.assertLogs(self.action.manager.log, level='ERROR') as cm:
            with self.assertRaises(Exception):
                self.action.restart_vm("rg", "vm-name")

        self.assertTrue(
            any("Unexpected error restarting VM" in log for log in cm.output),
            f"Expected 'Unexpected error restarting VM' in logs but got: {cm.output}",
        )
        self.action.client.virtual_machines.begin_start.assert_called_once_with("rg", "vm-name")

    # --- TESTING _wait_for_vm_stable_state() --- ###

    @patch('time.sleep', return_value=None)  # Mock sleep to avoid delays
    def test_wait_for_vm_stable_state_vm_succeeds_immediately(self, mock_sleep):
        """Test that the VM reaches 'Succeeded' state without delay."""
        self.mock_client.virtual_machines.get.return_value.provisioning_state = "Succeeded"
        result = self.action._wait_for_vm_stable_state("rg", "vm-name")
        self.assertTrue(result)
        self.mock_client.virtual_machines.get.assert_called_once_with(
            "rg", "vm-name", expand='instanceView'
        )
        mock_sleep.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_wait_for_vm_stable_state_vm_remains_updating_times_out(self, mock_sleep):
        """Test that the function times out when the VM remains in 'Updating' state."""
        self.mock_client.virtual_machines.get.return_value.provisioning_state = "Updating"
        with self.assertLogs(self.manager.log, level="WARNING") as log:
            result = self.action._wait_for_vm_stable_state("rg", "vm-name")
        self.assertFalse(result)
        self.assertIn("Timeout waiting for VM 'vm-name' to stabilize.", log.output[-1])
        self.assertGreater(self.mock_client.virtual_machines.get.call_count, 1)
        mock_sleep.assert_called()

    @patch('time.sleep', return_value=None)
    def test_wait_for_vm_stable_state_azure_error_during_vm_check(self, mock_sleep):
        """Test that an AzureError during VM status check is handled and logged."""
        self.mock_client.virtual_machines.get.side_effect = AzureError("VM Fetch Failed")
        with self.assertLogs(self.manager.log, level="ERROR") as log:
            result = self.action._wait_for_vm_stable_state("rg", "vm-name")
        self.assertFalse(result)
        self.assertIn("Azure error while checking VM 'vm-name': VM Fetch Failed", log.output[0])
        mock_sleep.assert_not_called()

    @patch('time.sleep', return_value=None)
    def test_wait_for_vm_stable_state_unexpected_exception_during_vm_check(self, mock_sleep):
        """Test that an unexpected exception during VM status check is handled and logged."""
        self.mock_client.virtual_machines.get.side_effect = Exception("Unexpected Error")
        with self.assertLogs(self.manager.log, level="ERROR") as log:
            result = self.action._wait_for_vm_stable_state("rg", "vm-name")
        self.assertFalse(result)
        self.assertIn(
            "Unexpected error while checking VM 'vm-name': Unexpected Error", log.output[0]
        )
        mock_sleep.assert_not_called()

    # --- TESTING THREADHELPER --- ###

    @patch.object(
        ThreadHelper,
        'execute_in_parallel',
        return_value=(["mock_resource"], ["Mock Exception 1", "Mock Exception 2"]),
    )
    def test_threadhelper_processes_exceptions_only(self, mock_thread_helper):
        """Test that exceptions returned from
        ThreadHelper.execute_in_parallel are logged properly."""

        # Simulate calling ThreadHelper.execute_in_parallel and capture logs
        with self.assertLogs(self.action.manager.log, level='ERROR') as cm:
            _, exceptions = ThreadHelper.execute_in_parallel(
                resources=["mock_resource"],
                event=None,
                execution_method=lambda r: r,  # Dummy method, since execution isn't the focus
                executor_factory=self.action.executor_factory,
                log=self.action.manager.log,
            )

            # Process only exceptions
            if exceptions:
                self.action.manager.log.error(f"Exceptions occurred: {exceptions}")

        self.assertIn("Exceptions occurred: ['Mock Exception 1', 'Mock Exception 2']", cm.output[0])

    # --- TESTING LOGGING ON SKIPPED STATES --- #

    def test_process_resources_skipped_disks(self):
        """Test that disks in SKIPPED_STATES are logged and not processed."""
        resources = [
            {'name': 'disk1', 'properties': {'diskState': 'ActiveSAS'}},
            {'name': 'disk2', 'properties': {'diskState': 'ReadyToUpload'}},
        ]

        with self.assertLogs(self.action.manager.log, level='INFO') as cm:
            self.action._process_resources(resources)

        self.assertIn("Skipping disk 'disk1'", cm.output[0])
        self.assertIn("Skipping disk 'disk2'", cm.output[1])


# Polling stays on in playback so the recorded poll requests are replayed, which
# @strict_cassette requires.
@requires_arm_polling
class DiskSnapshotTest(BaseTest):

    now = datetime.datetime(2026, 1, 2, 3, 4, 5)

    @staticmethod
    def _disk_id(disk_name):
        return (
            f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}/resourceGroups/test_disk'
            f'/providers/Microsoft.Compute/disks/{disk_name}'
        )

    def _snapshot_name_for(self, disk_name):
        return DiskSnapshotAction.snapshot_name(disk_name, self._disk_id(disk_name), self.now)

    def _load_snapshot_policy(self, name='test-azure-disk-snapshot', **options):
        with self.sign_out_patch():
            return self.load_policy({
                'name': name,
                'resource': 'azure.disk',
                'actions': [{'type': 'snapshot', **options}],
            }, validate=True)

    def _snapshot_body_for(self, tags, name='test-azure-disk-snapshot', **options):
        action = self._load_snapshot_policy(name, **options).resource_manager.actions[0]
        disk = {
            'name': 'cctest-snapshot-disk',
            'id': self._disk_id('cctest-snapshot-disk'),
            'location': 'southcentralus',
            'tags': tags,
        }
        return action.snapshot_body(disk)

    def _snapshot_policy(self, name_pattern, **options):
        return self.load_policy({
            'name': 'test-azure-disk-snapshot',
            'resource': 'azure.disk',
            'filters': [{'type': 'value', 'key': 'name', 'op': 'regex', 'value': name_pattern}],
            'actions': [{'type': 'snapshot', **options}],
        }, validate=True)

    def _run_snapshot_policy(self, name_pattern, **options):
        return self._snapshot_policy(name_pattern, **options).run()

    def _snapshots_in(self, resource_group):
        client = self.session.client('azure.mgmt.compute.ComputeManagementClient')
        return list(client.snapshots.list_by_resource_group(resource_group))

    def test_snapshot_schema_registers_the_action(self):
        p = self._load_snapshot_policy()

        assert isinstance(p.resource_manager.actions[0], DiskSnapshotAction)

    def test_snapshot_schema_accepts_boolean_incremental(self):
        p = self._load_snapshot_policy(incremental=False)

        assert p.resource_manager.actions[0].data['incremental'] is False

    def test_snapshot_schema_rejects_misspelled_option(self):
        with pytest.raises(PolicyValidationError, match="'incremntal' was unexpected"):
            self._load_snapshot_policy(incremntal=False)

    def test_snapshot_schema_rejects_non_boolean_incremental(self):
        with pytest.raises(PolicyValidationError, match="'yes' is not of type 'boolean'"):
            self._load_snapshot_policy(incremental='yes')

    def test_snapshot_body_copies_the_disk_and_defaults_to_incremental(self):
        disk_tags = {'testtag': 'testvalue'}

        body = self._snapshot_body_for(disk_tags)

        assert body == {
            'location': 'southcentralus',
            'creation_data': {
                'create_option': 'Copy',
                'source_resource_id': self._disk_id('cctest-snapshot-disk'),
            },
            'incremental': True,
            'tags': {'testtag': 'testvalue', 'custodian_snapshot': 'test-azure-disk-snapshot'},
        }
        assert disk_tags == {'testtag': 'testvalue'}

    def test_snapshot_body_full_copy_when_incremental_is_false(self):
        assert self._snapshot_body_for({}, incremental=False)['incremental'] is False

    def test_snapshot_body_replaces_a_marker_tag_in_any_case(self):
        body = self._snapshot_body_for({'Custodian_Snapshot': 'old'})

        assert body['tags'] == {'custodian_snapshot': 'test-azure-disk-snapshot'}

    def test_snapshot_body_skips_the_mark_for_op_tag(self):
        body = self._snapshot_body_for({'custodian_status': 'delete@2026/11/01', 'env': 'dev'})

        assert body['tags'] == {'env': 'dev', 'custodian_snapshot': 'test-azure-disk-snapshot'}

    def test_snapshot_body_caps_the_marker_at_256_characters(self):
        body = self._snapshot_body_for(None, name='p' * 300)

        assert body['tags'] == {'custodian_snapshot': 'p' * 256}

    def test_snapshot_failure_of_any_kind_does_not_stop_other_disks(self):
        action = self._load_snapshot_policy().resource_manager.actions[0]
        disks_without_ids = [{'name': 'cctest-no-id-1'}, {'name': 'cctest-no-id-2'}]

        with self.assertLogs('custodian.azure.AzureBaseAction', level='ERROR') as logs:
            with pytest.raises(KeyError):
                action.process(disks_without_ids)

        assert any("'cctest-no-id-1'" in line for line in logs.output)
        assert any("'cctest-no-id-2'" in line for line in logs.output)

    def test_snapshot_name_appends_timestamp_to_short_disk_name(self):
        name = self._snapshot_name_for('cctestvm_OsDisk_1_81338ced63fa4855b8a5f3e2bab5213c')

        assert name == 'cctestvm_OsDisk_1_81338ced63fa4855b8a5f3e2bab5213c-20260102030405'

    def test_snapshot_name_keeps_whole_disk_name_at_80_characters(self):
        disk_name = 'a' * 65

        assert self._snapshot_name_for(disk_name) == f'{disk_name}-20260102030405'

    def test_snapshot_name_truncates_and_hashes_past_80_characters(self):
        name = self._snapshot_name_for('a' * 66)

        assert name == 'a' * 56 + '-af248e7c-20260102030405'

    def test_snapshot_name_keeps_truncated_names_unique(self):
        first = self._snapshot_name_for('a' * 65 + '1')
        second = self._snapshot_name_for('a' * 65 + '2')

        assert first[:56] == second[:56]
        assert first != second

    def test_snapshot_name_ignores_disk_id_capitalization(self):
        disk_name = 'a' * 66
        disk_id = self._disk_id(disk_name)

        lower = DiskSnapshotAction.snapshot_name(disk_name, disk_id, self.now)
        upper = DiskSnapshotAction.snapshot_name(disk_name, disk_id.upper(), self.now)

        assert lower == upper

    @arm_template('disk-snapshot.json')
    @strict_cassette('disk-snapshot')
    def test_snapshot_creates_tagged_incremental_snapshot(self):
        disks = self._run_snapshot_policy('^cctest-snapshot-disk$')

        assert [d['name'] for d in disks] == ['cctest-snapshot-disk']
        snapshots = self._snapshots_in('test_disk-snapshot')
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.creation_data.source_resource_id.lower() == disks[0]['id'].lower()
        assert snapshot.creation_data.create_option == 'Copy'
        assert snapshot.incremental is True
        assert snapshot.tags == {
            'testtag': 'testvalue',
            'custodian_snapshot': 'test-azure-disk-snapshot',
        }
        assert snapshot.provisioning_state == 'Succeeded'

    @arm_template('disk-snapshot-full.json')
    @strict_cassette('disk-snapshot-full')
    def test_snapshot_full_copy_when_incremental_is_false(self):
        disks = self._run_snapshot_policy('^cctest-snapshot-full-disk$', incremental=False)

        assert [d['name'] for d in disks] == ['cctest-snapshot-full-disk']
        snapshots = self._snapshots_in('test_disk-snapshot-full')
        assert len(snapshots) == 1
        assert snapshots[0].creation_data.source_resource_id.lower() == disks[0]['id'].lower()
        assert snapshots[0].incremental is False

    @arm_template('disk-snapshot-tag-limit.json')
    @strict_cassette('disk-snapshot-tag-limit')
    def test_snapshot_failure_raises_after_snapshotting_other_disks(self):
        p = self._snapshot_policy('^cctest-snapshot-limit-')
        disks = sorted(p.resource_manager.resources(), key=lambda d: d['name'])
        # The failing disk must come first, or this can't tell "keep going" from "stop".
        assert [d['name'] for d in disks] == ['cctest-snapshot-limit-a', 'cctest-snapshot-limit-b']

        with pytest.raises(HttpResponseError, match='Too many tags specified'):
            p.resource_manager.actions[0].process(disks)

        snapshots = self._snapshots_in('test_disk-snapshot-tag-limit')
        sources = [s.creation_data.source_resource_id.rsplit('/', 1)[-1] for s in snapshots]
        assert sources == ['cctest-snapshot-limit-b']
