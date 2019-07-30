# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import json
import logging
import os
import tempfile
from datetime import datetime

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from azure.common import AzureHttpError
from azure.mgmt.eventgrid.models import \
    StorageQueueEventSubscriptionDestination, StringInAdvancedFilter, EventSubscriptionFilter
from c7n_azure import entry, constants
from c7n_azure.azure_events import AzureEventSubscription, AzureEvents
from c7n_azure.provider import Azure
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities as Storage
from c7n_azure.utils import ResourceIdParser

from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.utils import local_session

log = logging.getLogger("c7n_azure.container-host")
max_dequeue_count = 2
policy_update_seconds = 60
queue_poll_seconds = 15
jitter_seconds = 10
queue_timeout_seconds = 5 * 60
queue_message_count = 5


class Host:

    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        log.info("Running Azure Cloud Custodian Self-Host")

        if not Host.has_required_params():
            return

        load_resources()
        self.session = local_session(Session)

        # Load configuration
        self.options = Host.build_options()
        self.policy_storage_uri = os.getenv(constants.ENV_CONTAINER_POLICY_STORAGE)
        self.event_queue_name = os.getenv(constants.ENV_CONTAINER_EVENT_QUEUE_NAME)
        self.event_queue_id = os.getenv(constants.ENV_CONTAINER_EVENT_QUEUE_ID)

        # Prepare storage bits
        self.policy_blob_client = None
        self.blob_cache = {}
        self.queue_storage_account = self.prepare_queue_storage(
            self.event_queue_id,
            self.event_queue_name)

        self.queue_service = None

        # Track required event subscription updates
        self.require_event_update = False

        # Policy cache and dictionary
        self.policy_cache = tempfile.mkdtemp()
        self.policies = {}

        # Configure scheduler
        self.scheduler = BlockingScheduler()
        logging.getLogger('apscheduler.executors.default').setLevel(logging.ERROR)

        # Schedule recurring policy updates
        self.scheduler.add_job(self.update_policies,
                               'interval',
                               seconds=policy_update_seconds,
                               id="update_policies",
                               next_run_time=datetime.now())

        # Schedule recurring queue polling
        self.scheduler.add_job(self.poll_queue,
                               'interval',
                               seconds=queue_poll_seconds,
                               id="poll_queue")

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
            self.policy_blob_client = Storage.get_blob_client_by_uri(self.policy_storage_uri,
                                                                     self.session)
        (client, container, prefix) = self.policy_blob_client

        try:
            # All blobs with YAML extension
            blobs = [b for b in client.list_blobs(container) if Host.has_yaml_ext(b.name)]
        except AzureHttpError as e:
            # If blob methods are failing don't keep
            # a cached client
            self.policy_blob_client = None
            raise e

        # Filter to hashes we have not seen before
        new_blobs = [b for b in blobs
                     if b.properties.content_settings.content_md5 != self.blob_cache.get(b.name)]

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

            client.get_blob_to_path(container, blob.name, policy_path)
            self.load_policy(policy_path, policies_copy)
            self.blob_cache.update({blob.name: blob.properties.content_settings.content_md5})

        # Assign our copy back over the original
        self.policies = policies_copy

        if self.require_event_update:
            self.update_event_subscriptions()

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

                        # Update periodic and set event update flag
                        self.update_periodic(p)
                        if p.data.get('mode', {}).get('events'):
                            self.require_event_update = True

            except Exception as exc:
                log.error('Invalid policy file %s %s' % (path, exc))

    def unload_policy_file(self, path, policies):
        """
        Unload a policy file that has changed or been removed.
        Take the copy from disk and pop all policies from dictionary
        and update scheduled jobs and event registrations.
        """
        with open(path, "r") as stream:
            try:
                policy_config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                log.warning('Failure loading cached policy for cleanup %s %s' % (path, exc))
                os.unlink(path)
                return

        removed = [policies.pop(p['name']) for p in policy_config.get('policies', [])]
        log.info('Removing policies %s' % removed)

        # update periodic
        periodic_names = \
            [p['name'] for p in policy_config['policies'] if p.get('mode', {}).get('schedule')]
        periodic_to_remove = \
            [p for p in periodic_names if p in [j.id for j in self.scheduler.get_jobs()]]

        for name in periodic_to_remove:
            self.scheduler.remove_job(job_id=name)

        # update event
        event_names = \
            [p['name'] for p in policy_config['policies'] if p.get('mode', {}).get('events')]

        if event_names:
            self.require_event_update = True

        os.unlink(path)

        return path

    def update_periodic(self, policy):
        """
        Update scheduled policies using cron type
        periodic scheduling.
        """
        if policy.data.get('mode', {}).get('schedule'):
            trigger = CronTrigger.from_crontab(policy.data['mode']['schedule'])
            trigger.jitter = jitter_seconds
            self.scheduler.add_job(self.run_policy,
                                   trigger,
                                   id=policy.name,
                                   name=policy.name,
                                   args=[policy, None, None],
                                   coalesce=True,
                                   max_instances=1,
                                   replace_existing=True,
                                   misfire_grace_time=20)

    def update_event_subscriptions(self):
        """
        Find unique list of all subscribed events and
        update a single event subscription to channel
        them to an Azure Queue.
        """
        log.info('Updating event grid subscriptions')
        destination = \
            StorageQueueEventSubscriptionDestination(resource_id=self.queue_storage_account.id,
                                                     queue_name=self.event_queue_name)

        # Get total unique event list to use in event subscription
        policy_items = self.policies.items()
        events_lists = [v['policy'].data.get('mode', {}).get('events') for n, v in policy_items]
        flat_events = [e for l in events_lists if l for e in l if e]
        resolved_events = AzureEvents.get_event_operations(flat_events)
        unique_events = set(resolved_events)

        # Build event filter strings
        advance_filter = StringInAdvancedFilter(key='Data.OperationName', values=unique_events)
        event_filter = EventSubscriptionFilter(advanced_filters=[advance_filter])

        # Update event subscription
        AzureEventSubscription.create(destination,
                                      self.event_queue_name,
                                      self.session.get_subscription_id(),
                                      self.session, event_filter)

        self.require_event_update = False

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
                self.session)

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
            if operation_name in events:
                self.scheduler.add_job(self.run_policy,
                                       id=k + event['id'],
                                       name=k,
                                       args=[v['policy'],
                                             event,
                                             None],
                                       misfire_grace_time=60 * 3)

    def run_policy(self, policy, event, context):
        try:
            policy.push(event, context)
        except Exception as e:
            log.error(
                "Exception running policy: %s error: %s",
                policy.name, e)

    def prepare_queue_storage(self, queue_resource_id, queue_name):
        """
        Create a storage client using unusual ID/group reference
        as this is what we require for event subscriptions
        """
        storage_client = self.session.client('azure.mgmt.storage.StorageManagementClient')

        account = storage_client.storage_accounts.get_properties(
            ResourceIdParser.get_resource_group(queue_resource_id),
            ResourceIdParser.get_resource_name(queue_resource_id))

        Storage.create_queue_from_storage_account(account,
                                                  queue_name,
                                                  self.session)
        return account

    @staticmethod
    def has_required_params():
        required = [
            constants.ENV_CONTAINER_POLICY_STORAGE,
            constants.ENV_CONTAINER_EVENT_QUEUE_NAME,
            constants.ENV_CONTAINER_EVENT_QUEUE_ID
        ]

        missing = [r for r in required if os.getenv(r) is None]

        if missing:
            log.error('Missing REQUIRED environment variable(s): %s' % ', '.join(missing))
            return False

        return True

    @staticmethod
    def build_options():
        """
        Accept some CLI/Execution options as environment
        variables to apply global config across all policy
        executions.
        """
        output_dir = os.environ.get(constants.ENV_CONTAINER_OPTION_OUTPUT_DIR)

        if not output_dir:
            output_dir = tempfile.mkdtemp()
            log.warning('Output directory not specified.  Using directory: %s' % output_dir)

        config = Config.empty(
            **{
                'log_group': os.environ.get(constants.ENV_CONTAINER_OPTION_LOG_GROUP),
                'metrics': os.environ.get(constants.ENV_CONTAINER_OPTION_METRICS),
                'output_dir': output_dir
            }
        )

        return Azure().initialize(config)

    @staticmethod
    def has_yaml_ext(filename):
        return filename.lower().endswith(('.yml', '.yaml'))


if __name__ == "__main__":
    Host()

# Need to manually initialize c7n_azure
entry.initialize_azure()
