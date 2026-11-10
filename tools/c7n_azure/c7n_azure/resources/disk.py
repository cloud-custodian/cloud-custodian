# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time
from c7n_azure import constants
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import DEFAULT_TAG
from c7n_azure.utils import ResourceIdParser, StringUtils, ThreadHelper
from azure.core.exceptions import AzureError


@resources.register('disk')
class Disk(ArmResourceManager):
    """Disk Resource

    :example:

    This policy will find all data disks that are not being managed by a VM.

    .. code-block:: yaml

        policies:
          - name: orphaned-disk
            resource: azure.disk
            filters:
              - type: value
                key: managedBy
                value: null

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Storage']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('disks', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.diskState',
            'sku.name'
        )
        resource_type = 'Microsoft.Compute/disks'


@Disk.action_registry.register('modify-disk-type')
class ModifyDiskTypeAction(AzureBaseAction):
    """
    Action to modify the SKU type of Azure managed disks.

    **Key Features**:

    - **Parallel Processing**:
      Handles unattached and attached disks in parallel.

    - **Optimized Grouping**:
      Groups disks attached to the same VM to minimize the number of
      deallocate/restart operations.

    - **Thread Pools**:
      Uses separate thread pools for unattached/reserved and attached disk processing.

    **Supported SKUs**:
    - ``PremiumV2_LRS``
    - ``Standard_LRS``
    - ``StandardSSD_ZRS``
    - ``Premium_ZRS``
    - ``UltraSSD_LRS``
    - ``Premium_LRS``
    - ``StandardSSD_LRS``

    :param new_sku:
        The target SKU for the disk. Must be one of the supported SKUs listed above.
    :type new_sku: str

    :param retries:
        Number of times to retry modifying the disk type if an error occurs
        (e.g., transient Azure API issues).
    :type retries: int


    :param delay:
        Delay (in seconds) between retries. A short delay can help avoid throttling or temporary
        service unavailability.
    :type delay: int

    .. note::

       - This action requires deallocating any VM that has an attached disk targeted by the SKU

        change, which will result in VM downtime.

       - Ensure the target SKU is available in the region where the disk resides.

       - Changing certain disk types (e.g., ``UltraSSD_LRS``)

        may require the VM size to support the chosen SKU.

       - Some SKUs may incur different costs and performance implications.

        Check Azure documentation for details.

    **Examples**

     Change attached ``Premium_LRS`` disks to ``Standard_LRS``:

    .. code-block:: yaml

        policies:
          - name: change-attached-disk-sku
            resource: azure.disk
            filters:
              - type: value
                key: properties.diskState
                op: eq
                value: Attached
              - type: value
                key: sku.name
                op: eq
                value: Premium_LRS
            actions:
              - type: modify-disk-type
                new_sku: Standard_LRS
                retries: 2
                delay: 10

    Change all unattached disks to ``Premium_LRS``:

    .. code-block:: yaml

        policies:
          - name: change-unattached-disk-sku
            resource: azure.disk
            filters:
              - type: value
                key: properties.diskState
                op: eq
                value: Unattached
            actions:
              - type: modify-disk-type
                new_sku: Premium_LRS
                retries: 3
                delay: 5

    For more information on Azure managed disk SKUs and their requirements, refer
    to the official Azure documentation.
    """

    MAX_VM_WAIT_TIME = 300  # Max wait time for VMs in seconds (5 mins)
    VM_CHECK_INTERVAL = 20  # Interval for checking VM state (20 secs)

    VALID_SKUS = [
        constants.DISK_SKU_STANDARD_LRS,
        constants.DISK_SKU_STANDARDSSD_LRS,
        constants.DISK_SKU_PREMIUM_LRS,
        constants.DISK_SKU_PREMIUMV2_LRS,
        constants.DISK_SKU_STANDARDSSD_ZRS,
        constants.DISK_SKU_PREMIUM_ZRS,
        constants.DISK_SKU_ULTRASSD_LRS,
    ]

    SUPPORTED_STATES = {
        "Attached": {   # Disks states for attached disks
            constants.DISK_STATE_ATTACHED,
            constants.DISK_STATE_ACTIVE_SAS_FROZEN,
            constants.DISK_STATE_FROZEN,
        },
        # Disks states for unattached disks
        "Unattached": {constants.DISK_STATE_UNATTACHED, constants.DISK_STATE_RESERVED}
    }
    # Disk states that not allowed to change from due to the VM state the disk is associated with.
    SKIPPED_STATES = {
        constants.DISK_STATE_ACTIVE_SAS,
        constants.DISK_STATE_ACTIVE_UPLOAD,
        constants.DISK_STATE_READY_TO_UPLOAD,
    }

    schema = type_schema(
        'modify-disk-type',
        required=['new_sku'],
        **{
            'new_sku': {'type': 'string', 'enum': VALID_SKUS},
            'retries': {'type': 'integer', 'minimum': 1, 'default': 3},
            'delay': {'type': 'integer', 'minimum': 1, 'default': 5},
        },
    )
    schema_alias = True

    def __init__(self, data=None, manager=None):
        super(ModifyDiskTypeAction, self).__init__(data, manager)
        self.new_sku = self.data['new_sku']
        self.retries = self.data.get('retries', 3)
        self.delay = self.data.get('delay', 5)
        self._vm_disk_map = {}

    def validate(self):
        """
        Validate the current configuration to ensure it meets requirements:
        - new_sku must be in VALID_SKUS
        - retries and delay must be positive integers
        """
        if self.new_sku not in self.VALID_SKUS:
            raise ValueError(
                f"The specified new_sku '{self.new_sku}' is invalid. "
                f"Valid options: {', '.join(self.VALID_SKUS)}."
            )
        self.log.info(f"Validated new_sku: {self.new_sku} is valid.")

        if not isinstance(self.retries, int) or self.retries < 1:
            raise ValueError(
                f"Invalid 'retries' value: {self.retries}. Must be a positive integer."
            )
        self.log.info(f"Validated retries: {self.retries}.")

        if not isinstance(self.delay, int) or self.delay < 1:
            raise ValueError(f"Invalid 'delay' value: {self.delay}. Must be a positive integer.")
        self.log.info(f"Validated delay: {self.delay} seconds.")

        self.log.info("Validation successful for ModifyDiskTypeAction.")

    def _prepare_processing(self):
        """
        Prepare clients or sessions before processing resources.
        """
        self.client = self.manager.get_client('azure.mgmt.compute.ComputeManagementClient')

    def _process_resource(self, resource):
        """
        Hook for per-resource pre-processing if needed;
        calls parent base class method by default.
        """
        return super()._process_resource(resource)

    def _process_resources(self, resources, event=None):
        """
        Main entry point for disk processing. Divided into two flows:
        - Unattached/Reserved disks (processed directly in parallel).
        - Attached disks (grouped by VM, deallocated, updated, restarted).
        """
        self._prepare_processing()

        # Skip disks in states we do not process
        skipped = [
            r for r in resources if r.get('properties', {}).get('diskState') in self.SKIPPED_STATES
        ]

        for disk in skipped:
            self.manager.log.info(
                f"Skipping disk '{disk['name']}' in state '{disk['properties']['diskState']}'."
            )

        # Separate disks by whether they are unattached/reserved or attached
        unattached_or_reserved_disks = [
            r
            for r in resources
            if r.get('properties', {}).get('diskState') in self.SUPPORTED_STATES["Unattached"]
        ]

        attached_disks = [
            r
            for r in resources
            if r.get('properties', {}).get('diskState') in self.SUPPORTED_STATES["Attached"]
        ]

        # Process unattached/reserved disks in parallel
        if unattached_or_reserved_disks:
            processed_resources, exceptions = ThreadHelper.execute_in_parallel(
                resources=unattached_or_reserved_disks,
                event=event,
                executor_factory=self.executor_factory,
                execution_method=self._process_unattached_or_reserved_disk,
                log=self.manager.log,
                max_workers=constants.DEFAULT_MAX_THREAD_WORKERS,  # Adjust if needed
                chunk_size=constants.DEFAULT_CHUNK_SIZE,  # Adjust if needed
            )
            self.manager.log.info(
                f"Finished processing unattached/reserved disks. "
                f"{len(processed_resources)} resources processed."
            )
            if exceptions:
                self.manager.log.error(f"Exceptions occurred: {exceptions}")

        # If there are no attached disks, we can stop here
        if not attached_disks:
            return

        # Group attached disks by VM
        for disk in attached_disks:
            vm_id = disk['managedBy']
            self.group_attached_disks_by_vm(vm_id, disk)

        # Process attached disks grouped by VM in parallel
        processed_vm_groups, exceptions = ThreadHelper.execute_in_parallel(
            resources=list(self._vm_disk_map.items()),
            event=event,
            executor_factory=self.executor_factory,
            execution_method=self._process_attached_vm_disks,
            log=self.manager.log,
            max_workers=constants.DEFAULT_MAX_THREAD_WORKERS,
            chunk_size=1,  # Set to 1 so each VM-disk group is processed individually
        )
        self.manager.log.info(
            f"Finished processing attached disks. "
            f"{len(processed_vm_groups)} VM-disk groups processed."
        )
        if exceptions:
            self.manager.log.error(f"Exceptions occurred: {exceptions}")

    def _process_unattached_or_reserved_disk(self, disks, event=None):
        """
        Process a chunk/list of unattached or reserved disks.
        """
        for disk in disks:
            try:
                self.manager.log.info(f"Processing disk '{disk['name']}'.")
                self.update_disk_sku_with_retries(disk)
                self.manager.log.info(f"Finished processing disk '{disk['name']}'.")
            except Exception as e:
                self.manager.log.error(f"Failed processing disk '{disk['name']}': {e}")

    def _process_attached_vm_disks(self, vm_disk_groups, event=None):
        """
        Process attached disks for multiple VMs:
        1) Check VM provisioning and power state.
        2) Wait if in transitional states (Creating/Updating).
        3) Skip VMs in failed or unknown states.
        4) If running, deallocate → update disks → restart.
        """
        for vm_id, disks in vm_disk_groups:
            vm_rg, vm_name = self.extract_resource_group_and_name(vm_id)

            # Filter out disks that already match self.new_sku
            disks_to_update = [d for d in disks if d.get("sku", {}).get("name") != self.new_sku]
            if not disks_to_update:
                self.manager.log.info(f"No disks require update for VM '{vm_name}'. Skipping.")
                continue

            try:
                vm = self.client.virtual_machines.get(vm_rg, vm_name, expand='instanceView')

                # Wait for VM to become stable (not Creating/Updating)
                if not self._wait_for_vm_stable_state(vm_rg, vm_name):
                    self.manager.log.info(f"Skipping VM '{vm_name}' due to unstable state.")
                    continue

                vm_state = self._assess_vm_state(vm)

                if not vm_state['can_proceed']:
                    self.manager.log.info(
                        f"Skipping VM '{vm_name}' due to state: {vm_state['reason']}"
                    )
                    continue

                # If VM is running, deallocate before updating
                if vm_state['should_deallocate']:
                    self.deallocate_vm(vm_rg, vm_name)

                # Update the disks
                for disk in disks_to_update:
                    self.update_disk_sku_with_retries(disk)

                # Restart VM if needed
                if vm_state['should_deallocate']:
                    self.restart_vm(vm_rg, vm_name)

            except AzureError as e:
                self.manager.log.error(f"Azure error while processing VM '{vm_name}': {e}")
            except Exception as e:
                self.manager.log.error(f"Unexpected error processing VM '{vm_name}': {e}")

    def _wait_for_vm_stable_state(self, vm_rg, vm_name):
        """
        Waits for a VM to exit transient states (Creating, Updating).
        Returns True if VM becomes stable, False if timeout occurs.
        """
        start_time = time.time()

        while time.time() - start_time < self.MAX_VM_WAIT_TIME:
            try:
                vm = self.client.virtual_machines.get(vm_rg, vm_name, expand='instanceView')
                prov_state = (vm.provisioning_state or '').capitalize()

                if prov_state == "Succeeded":
                    return True  # Only continue if Succeeded

                self.manager.log.info(
                    f"VM '{vm_name}' is in provisioning state '{prov_state}'. Waiting..."
                )
                time.sleep(self.VM_CHECK_INTERVAL)

            except AzureError as e:
                self.manager.log.error(f"Azure error while checking VM '{vm_name}': {e}")
                return False
            except Exception as e:
                self.manager.log.error(f"Unexpected error while checking VM '{vm_name}': {e}")
                return False

        self.manager.log.warning(f"Timeout waiting for VM '{vm_name}' to stabilize.")
        return False  # Timeout, VM is still not stable

    def _assess_vm_state(self, vm):
        """
        Evaluates the provisioning and power state of the VM.
        Determines whether disk updates can proceed.
        """
        forbidden_prov_states = {'Creating', 'Updating', 'Deleting', 'Failed', 'Canceled'}
        prov_state = (vm.provisioning_state or '').capitalize()

        if prov_state in forbidden_prov_states:
            return {
                'can_proceed': False,
                'should_deallocate': False,
                'reason': f"Provisioning state '{prov_state}'",
            }

        power_state = 'Unknown'
        if vm.instance_view and vm.instance_view.statuses:
            for status in vm.instance_view.statuses:
                if status.code.lower().startswith('powerstate/'):
                    power_state = status.code.split('/', 1)[-1].capitalize()
                    break

        if power_state == 'Deallocated':
            return {
                'can_proceed': True,
                'should_deallocate': False,
                'reason': "VM is already deallocated",
            }

        if power_state in ('Running', 'Stopped'):
            return {
                'can_proceed': True,
                'should_deallocate': True,
                'reason': f"Power state '{power_state}', will deallocate and update",
            }

        return {
            'can_proceed': False,
            'should_deallocate': False,
            'reason': f"Power state '{power_state}' is transitional or unknown",
        }

    def group_attached_disks_by_vm(self, vm_id, disk):
        """
        Group attached disks by VM to minimize repeated deallocate/restart cycles.
        """
        if vm_id not in self._vm_disk_map:
            self._vm_disk_map[vm_id] = []
        self._vm_disk_map[vm_id].append(disk)

    def update_disk_sku_with_retries(self, disk):
        """
        Update the SKU of a disk with retry logic, breaking out if the error indicates
        VM size/throughput constraints.
        """
        resource_group, disk_name = self.extract_resource_group_and_name(disk['id'])
        current_sku = disk.get("sku", {}).get("name")

        if current_sku == self.new_sku:
            self.manager.log.info(
                f"Disk '{disk['name']}' already has desired SKU '{self.new_sku}'."
            )
            return

        disk_update_info = {"sku": {"name": self.new_sku}, "location": disk.get("location")}

        for attempt in range(self.retries):
            try:
                self.manager.log.info(
                    f"Updating disk '{disk_name}' to SKU '{self.new_sku}' (attempt {attempt + 1})."
                )
                self.client.disks.begin_update(resource_group, disk_name, disk_update_info).result()
                self.manager.log.info(
                    f"Successfully updated disk '{disk_name}' to SKU '{self.new_sku}'."
                )
                return
            except AzureError as e:
                self.manager.log.error(
                    f"AzureError on attempt {attempt + 1} for disk '{disk_name}': {e.message}"
                )
            except Exception as e:
                self.manager.log.error(f"Attempt {attempt + 1} failed for disk '{disk_name}': {e}")

            if attempt < self.retries - 1:
                time.sleep(self.delay)

        raise RuntimeError(f"Failed to update disk '{disk_name}' after {self.retries} attempts.")

    def deallocate_vm(self, resource_group, vm_name):
        """
        Deallocate a VM and wait for completion, with error handling.
        """
        try:
            vm = self.client.virtual_machines.get(resource_group, vm_name)
            self.manager.log.info(
                f"Deallocating VM '{vm_name}'. Current state: {vm.provisioning_state}"
            )
            operation = self.client.virtual_machines.begin_deallocate(resource_group, vm_name)
            operation.wait()
            self.manager.log.info(f"Successfully deallocated VM '{vm_name}'.")
        except AzureError as e:
            self.manager.log.error(f"Azure API error deallocating VM '{vm_name}': {e.message}")
            raise
        except Exception as e:
            self.manager.log.error(f"Unexpected error deallocating VM '{vm_name}': {e}")
            raise

    def restart_vm(self, resource_group, vm_name):
        """
        Restart a VM and wait for completion, with error handling.
        """
        try:
            self.manager.log.info(f"Restarting VM '{vm_name}'.")
            self.client.virtual_machines.begin_start(resource_group, vm_name).wait()
            self.manager.log.info(f"Successfully restarted VM '{vm_name}'.")
        except AzureError as e:
            self.manager.log.error(f"Azure API error restarting VM '{vm_name}': {e.message}")
            raise
        except Exception as e:
            self.manager.log.error(f"Unexpected error restarting VM '{vm_name}': {e}")
            raise

    @staticmethod
    def extract_resource_group_and_name(resource_id):
        """
        Extract the resource group and name from a resource ID.
        """
        resource_group = ResourceIdParser.get_resource_group(resource_id)
        resource_name = ResourceIdParser.get_resource_name(resource_id)
        return resource_group, resource_name


@Disk.action_registry.register('snapshot')
class DiskSnapshotAction(AzureBaseAction):
    """Create a snapshot of each disk.

    Snapshots go in the disk's resource group and are named
    ``<disk name>-<YYYYMMDDhhmmss>`` (UTC). Names over Azure's 80-character limit are
    shortened, with a hash of the disk ID added to keep them unique.

    ``incremental`` (default ``true``) stores only the changes since the disk's previous
    snapshot. Set it to ``false`` for a full copy. Azure supports only incremental
    snapshots of Ultra Disks and Premium SSD v2 disks, and finishes copying them after
    the action returns.

    Azure gives the snapshot the disk's encryption settings, including a customer-managed
    key. The snapshot gets the disk's tags, except the ``custodian_status`` tag from
    ``mark-for-op``, plus a ``custodian_snapshot`` tag set to the policy name. A snapshot
    isn't taken if that comes to more than Azure's limit of 50 tags.

    If a snapshot fails, snapshots of the remaining disks are still taken, then the
    action raises so later actions in the policy don't run.

    Needs at least ``Microsoft.Compute/disks/read``, ``Microsoft.Compute/snapshots/write``
    and ``Microsoft.Compute/snapshots/read``.

    :example:

    Take a snapshot of every disk tagged ``backup: daily``:

    .. code-block:: yaml

        policies:
          - name: azure-disk-snapshot-daily
            resource: azure.disk
            filters:
              - "tag:backup": daily
            actions:
              - type: snapshot
    """

    schema = type_schema('snapshot', incremental={'type': 'boolean'})

    def _process_resources(self, resources, event):
        # The base class logs and swallows errors outside pytest, so a later action such
        # as delete would still run. Snapshot the rest, then raise.
        self._prepare_processing()
        failures = []
        for resource in resources:
            try:
                self._log_modified_resource(resource, self._process_resource(resource))
            except Exception as e:
                self.log.error(
                    "Snapshot of disk '%s' in resource group '%s' failed: %s",
                    resource.get('name'), resource.get('resourceGroup'), e,
                    exc_info=True, extra=self._get_action_log_metadata(resource))
                failures.append(e)
        if failures:
            raise failures[0]

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        # Imported here so the test harness's patch of utcnow takes effect.
        from c7n_azure.utils import utcnow

        name = self.snapshot_name(resource['name'], resource['id'], utcnow())
        self.client.snapshots.begin_create_or_update(
            resource['resourceGroup'], name, self.snapshot_body(resource)).result()
        return f"Created snapshot '{name}'"

    def snapshot_body(self, disk):
        """Return the request body that creates a snapshot of ``disk``."""
        tags = {
            k: v for k, v in (disk.get('tags') or {}).items()
            if k.lower() not in ('custodian_snapshot', DEFAULT_TAG)
        }
        tags['custodian_snapshot'] = self.manager.ctx.policy.name[:256]
        return {
            'location': disk['location'],
            'creation_data': {'create_option': 'Copy', 'source_resource_id': disk['id']},
            'incremental': self.data.get('incremental', True),
            'tags': tags,
        }

    @staticmethod
    def snapshot_name(disk_name, disk_id, now):
        """Return a valid Azure snapshot name, unique per disk and second."""
        stamp = now.strftime('%Y%m%d%H%M%S')
        name = f'{disk_name}-{stamp}'
        if len(name) <= 80:
            return name
        suffix = f'-{StringUtils.naming_hash(disk_id.lower())}-{stamp}'
        return disk_name[:80 - len(suffix)] + suffix
