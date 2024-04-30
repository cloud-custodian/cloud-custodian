# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import logging
import os
import tempfile
from datetime import datetime

import click
import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from azure.common import AzureHttpError
from azure.mgmt.eventgrid.models import (
    EventSubscriptionFilter, StorageQueueEventSubscriptionDestination)

from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n import resources
from c7n.utils import local_session
from c7n_azure import entry
from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from c7n_azure.constants import (CONTAINER_EVENT_TRIGGER_MODE,
                                 CONTAINER_TIME_TRIGGER_MODE,
                                 ENV_CONTAINER_OPTION_LOG_GROUP,
                                 ENV_CONTAINER_OPTION_METRICS,
                                 ENV_CONTAINER_OPTION_OUTPUT_DIR,
                                 ENV_CONTAINER_POLICY_URI,
                                 ENV_CONTAINER_QUEUE_NAME,
                                 ENV_CONTAINER_STORAGE_RESOURCE_ID)
from c7n_azure.provider import Azure
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities as Storage
from c7n_azure.utils import ResourceIdParser

log = logging.getLogger("c7n_azure.container-host")
max_dequeue_count = 2
policy_update_seconds = 60
queue_poll_seconds = 15
queue_timeout_seconds = 5 * 60
queue_message_count = 5


class Host:

    def __init__(self, storage_id, queue_name, policy_uri,
                 log_group=None, metrics=None, output_dir=None):
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        log.info("Running Azure Cloud Custodian Self-Host")

        resources.load_available()

        self.session = local_session(Session)
        self.storage_session = self.session
        storage_subscription_id = ResourceIdParser.get_subscription_id(storage_id)
        if storage_subscription_id != self.session.subscription_id:
            self.storage_session = Session(subscription_id=storage_subscription_id)

        # Load configuration
        self.options = Host.build_options(output_dir, log_group, metrics)
        self.policy_storage_uri = policy_uri
        self.event_queue_id = storage_id
        self.event_queue_name = queue_name

        # Default event queue name is the subscription ID
        if not self.event_queue_name:
            self.event_queue_name = self.session.subscription_id

        # Prepare storage bits
        self.policy_blob_client = None
        self.blob_cache = {}
        self.queue_storage_account = self.prepare_queue_storage(
            self.event_queue_id,
            self.event_queue_name)

        self.queue_service = None

        # Register event subscription
        self.update_event_subscription()

        # Policy cache and dictionary
        self.policy_cache = tempfile.mkdtemp()
        self.policies = {}

        # Configure scheduler
        self.scheduler = BlockingScheduler(Host.get_scheduler_config())
        logging.getLogger('apscheduler.executors.default').setLevel(logging.ERROR)
        logging.getLogger('apscheduler').setLevel(logging.ERROR)

        # Schedule recurring policy updates
        self.scheduler.add_job(self.update_policies,
                               'interval',
                               seconds=policy_update_seconds,
                               id="update_policies",
                               next_run_time=datetime.now(),
                               executor='threadpool')

        # Schedule recurring queue polling
        self.scheduler.add_job(self.poll_queue,
                               'interval',
                               seconds=queue_poll_seconds,
                               id="poll_queue",
                               executor='threadpool')

        self.scheduler.start()

    def update_policies(self):
        """
        Enumerate all policies from storage.
        Use the MD5 hashes in the enumerated policies
        and a local dictionary to decide if we should
        bother downloading/updating each blob.
        We maintain an on-disk policy cache for future
        features.
        """
        if not self.policy_blob_client:
            self.policy_blob_client = Storage.get_blob_client_by_uri(
                self.policy_storage_uri,
                self.storage_session
            )
        (client, container, _) = self.policy_blob_client

        try:
            # All blobs with YAML extension
            blobs = [b for b in client.list_blobs(container) if Host.has_yaml_ext(b.name)]
        except AzureHttpError as e:
            # If blob methods are failing don't keep
            # a cached client
            self.policy_blob_client = None
            raise e

        # Filter to hashes we have not seen before
        new_blobs = self._get_new_blobs(blobs)

        # Get all YAML files on disk that are no longer in blob storage
        cached_policy_files = [f for f in os.listdir(self.policy_cache)
                               if Host.has_yaml_ext(f)]

        removed_files = [f for f in cached_policy_files if f not in [b.name for b in blobs]]

        if not (removed_files or new_blobs):
            return

        # Update a copy so we don't interfere with
        # iterations on other threads
        policies_copy = self.policies.copy()

        for f in removed_files:
            path = os.path.join(self.policy_cache, f)
            self.unload_policy_file(path, policies_copy)

        # Get updated YML files
        for blob in new_blobs:
            policy_path = os.path.join(self.policy_cache, blob.name)
            if os.path.exists(policy_path):
                self.unload_policy_file(policy_path, policies_copy)
            elif not os.path.isdir(os.path.dirname(policy_path)):
                os.makedirs(os.path.dirname(policy_path))

            client.get_blob_to_path(container, blob.name, policy_path)
            self.load_policy(policy_path, policies_copy)
            self.blob_cache.update({blob.name: blob.content_settings.content_md5})

        # Assign our copy back over the original
        self.policies = policies_copy

    def _get_new_blobs(self, blobs):
        new_blobs = []
        for blob in blobs:
            md5_hash = blob.content_settings.content_md5
            if not md5_hash:
                blob, md5_hash = self._try_create_md5_content_hash(blob)
            if blob and md5_hash and md5_hash != self.blob_cache.get(blob.name):
                new_blobs.append(blob)
        return new_blobs

    def _try_create_md5_content_hash(self, blob):
        # Not all storage clients provide the md5 hash when uploading a file
        # so, we need to make sure that hash exists.
        (client, container, _) = self.policy_blob_client
        log.info("Applying md5 content hash to policy {}".format(blob.name))

        try:
            # Get the blob contents
            blob_bytes = client.get_blob_to_bytes(container, blob.name)

            # Re-upload the blob. validate_content ensures that the md5 hash is created
            client.create_blob_from_bytes(container, blob.name, blob_bytes.content,
                validate_content=True)

            # Re-fetch the blob with the new hash
            hashed_blob = client.get_blob_properties(container, blob.name)

            return hashed_blob, hashed_blob.content_settings.content_md5
        except AzureHttpError as e:
            log.warning("Failed to apply a md5 content hash to policy {}. "
                        "This policy will be skipped.".format(blob.name))
            log.error(e)
            return None, None

    def load_policy(self, path, policies):
        """
        Loads a YAML file and prompts scheduling updates
        :param path: Path to YAML file on disk
        :param policies: Dictionary of policies to update
        """
        with open(path, "r") as stream:
            try:
                policy_config = yaml.safe_load(stream)
                new_policies = PolicyCollection.from_data(policy_config, self.options)

                if new_policies:
                    for p in new_policies:
                        log.info("Loading Policy %s from %s" % (p.name, path))

                        p.validate()
                        policies.update({p.name: {'policy': p}})

                        # Update periodic
                        policy_mode = p.data.get('mode', {}).get('type')
                        if policy_mode == CONTAINER_TIME_TRIGGER_MODE:
                            self.update_periodic(p)
                        elif policy_mode != CONTAINER_EVENT_TRIGGER_MODE:
                            log.warning(
                                "Unsupported policy mode for Azure Container Host: {}. "
                                "{} will not be run. "
                                "Supported policy modes include \"{}\" and \"{}\"."
                                .format(
                                    policy_mode,
                                    p.data['name'],
                                    CONTAINER_EVENT_TRIGGER_MODE,
                                    CONTAINER_TIME_TRIGGER_MODE
                                )
                            )

            except Exception as exc:
                log.error('Invalid policy file %s %s' % (path, exc))

    def unload_policy_file(self, path, policies):
        """
        Unload a policy file that has changed or been removed.
        Take the copy from disk and pop all policies from dictionary
        and update scheduled jobs.
        """
        with open(path, "r") as stream:
            try:
                policy_config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                log.warning('Failure loading cached policy for cleanup %s %s' % (path, exc))
                os.unlink(path)
                return path

        try:
            # Some policies might have bad format, so they have never been loaded
            removed = [policies.pop(p['name'])
                       for p in policy_config.get('policies', [])
                       if p['name'] in policies]
            log.info('Removing policies %s' % removed)

            # update periodic
            periodic_names = \
                [p['name'] for p in policy_config.get('policies', [])
                 if p.get('mode', {}).get('schedule')]
            periodic_to_remove = \
                [p for p in periodic_names if p in [j.id for j in self.scheduler.get_jobs()]]

            for name in periodic_to_remove:
                self.scheduler.remove_job(job_id=name)
        except (AttributeError, KeyError) as exc:
            log.warning('Failure loading cached policy for cleanup %s %s' % (path, exc))

        os.unlink(path)
        return path

    def update_periodic(self, policy):
        """
        Update scheduled policies using cron type
        periodic scheduling.
        """
        trigger = CronTrigger.from_crontab(policy.data['mode']['schedule'])
        self.scheduler.add_job(Host.run_policy,
                               trigger,
                               id=policy.name,
                               name=policy.name,
                               args=[policy, None, None],
                               coalesce=True,
                               max_instances=1,
                               replace_existing=True,
                               misfire_grace_time=60)

    def update_event_subscription(self):
        """
        Create a single event subscription to channel
        all events to an Azure Queue.
        """
        log.info('Updating event grid subscriptions')
        destination = StorageQueueEventSubscriptionDestination(
            resource_id=self.queue_storage_account.id, queue_name=self.event_queue_name)

        # Build event filter
        event_filter = EventSubscriptionFilter(
            included_event_types=['Microsoft.Resources.ResourceWriteSuccess'])

        # Update event subscription
        AzureEventSubscription.create(destination,
                                      self.event_queue_name,
                                      self.session.get_subscription_id(),
                                      self.session, event_filter)

    def poll_queue(self):
        """
        Poll the Azure queue and loop until
        there are no visible messages remaining.
        """
        # Exit if we don't have any policies
        if not self.policies:
            return

        if not self.queue_service:
            self.queue_service = Storage.get_queue_client_by_storage_account(
                self.queue_storage_account,
                self.storage_session)

        while True:
            try:
                messages = Storage.get_queue_messages(
                    self.queue_service,
                    self.event_queue_name,
                    num_messages=queue_message_count,
                    visibility_timeout=queue_timeout_seconds)
            except AzureHttpError:
                self.queue_service = None
                raise

            if len(messages) == 0:
                break

            log.info('Pulled %s events to process while polling queue.' % len(messages))

            for message in messages:
                if message.dequeue_count > max_dequeue_count:
                    Storage.delete_queue_message(self.queue_service,
                                                 self.event_queue_name,
                                                 message=message)
                    log.warning("Event deleted due to reaching maximum retry count.")
                else:
                    # Run matching policies
                    self.run_policies_for_event(message)

                    # We delete events regardless of policy result
                    Storage.delete_queue_message(
                        self.queue_service,
                        self.event_queue_name,
                        message=message)

    def run_policies_for_event(self, message):
        """
        Find all policies subscribed to this event type
        and schedule them for immediate execution.
        """
        # Load up the event
        event = json.loads(base64.b64decode(message.content).decode('utf-8'))
        operation_name = event['data']['operationName']

        # Execute all policies matching the event type
        for k, v in self.policies.items():
            events = v['policy'].data.get('mode', {}).get('events')
            if not events:
                continue
            events = AzureEvents.get_event_operations(events)
            if operation_name.upper() in (event.upper() for event in events):
                self.scheduler.add_job(Host.run_policy,
                                       id=k + event['id'],
                                       name=k,
                                       args=[v['policy'],
                                             event,
                                             None],
                                       misfire_grace_time=60 * 3)

    def prepare_queue_storage(self, queue_resource_id, queue_name):
        """
        Create a storage client using unusual ID/group reference
        as this is what we require for event subscriptions
        """

        storage_client = self.storage_session \
            .client('azure.mgmt.storage.StorageManagementClient')

        account = storage_client.storage_accounts.get_properties(
            ResourceIdParser.get_resource_group(queue_resource_id),
            ResourceIdParser.get_resource_name(queue_resource_id))

        Storage.create_queue_from_storage_account(account,
                                                  queue_name,
                                                  self.session)
        return account

    @staticmethod
    def run_policy(policy, event, context):
        try:
            policy.push(event, context)
        except Exception:
            log.exception("Policy Failed: %s", policy.name)

    @staticmethod
    def build_options(output_dir=None, log_group=None, metrics=None):
        """
        Initialize the Azure provider to apply global config across all policy executions.
        """
        if not output_dir:
            output_dir = tempfile.mkdtemp()
            log.warning('Output directory not specified.  Using directory: %s' % output_dir)

        config = Config.empty(
            **{
                'log_group': log_group,
                'metrics': metrics,
                'output_dir': output_dir
            }
        )

        return Azure().initialize(config)

    @staticmethod
    def get_scheduler_config():
        if os.name == 'nt':
            executor = "apscheduler.executors.pool:ThreadPoolExecutor"
        else:
            executor = "apscheduler.executors.pool:ProcessPoolExecutor"

        return {
            'apscheduler.jobstores.default': {
                'type': 'memory'
            },
            'apscheduler.executors.default': {
                'class': executor,
                'max_workers': '4'
            },
            'apscheduler.executors.threadpool': {
                'type': 'threadpool',
                'max_workers': '20'
            },
            'apscheduler.job_defaults.coalesce': 'true',
            'apscheduler.job_defaults.max_instances': '1',
            'apscheduler.timezone': 'UTC',
        }

    @staticmethod
    def has_yaml_ext(filename):
        return filename.lower().endswith(('.yml', '.yaml'))

    @staticmethod
    @click.command(help="Periodically run a set of policies from an Azure storage container "
                        "against a single subscription. The host will update itself with new "
                        "policies and event subscriptions as they are added.")
    @click.option("--storage-id", "-q", envvar=ENV_CONTAINER_STORAGE_RESOURCE_ID, required=True,
                  help="The resource id of the storage account to create the event queue in")
    @click.option("--queue-name", "-n", envvar=ENV_CONTAINER_QUEUE_NAME,
                  help="The name of the event queue to create")
    @click.option("--policy-uri", "-p", envvar=ENV_CONTAINER_POLICY_URI, required=True,
                  help="The URI to the Azure storage container that holds the policies")
    @click.option("--log-group", "-l", envvar=ENV_CONTAINER_OPTION_LOG_GROUP,
                  help="Location to send policy logs")
    @click.option("--metrics", "-m", envvar=ENV_CONTAINER_OPTION_METRICS,
                  help="The resource name or instrumentation key for uploading metrics")
    @click.option("--output-dir", "-d", envvar=ENV_CONTAINER_OPTION_OUTPUT_DIR,
                  help="The directory for policy output")
    def cli(**kwargs):
        Host(**kwargs)


if __name__ == "__main__":
    # handle CLI commands
    Host.cli()

# Need to manually initialize c7n_azure
entry.initialize_azure()
