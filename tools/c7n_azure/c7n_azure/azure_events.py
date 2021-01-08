# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.eventgrid.models import EventSubscription, EventSubscriptionFilter
from c7n_azure.session import Session

from c7n.utils import local_session


class AzureEvents:
    """A mapping of resource types to events."""

    azure_events = {

        'AppServicePlanWrite': {
            'resource_provider': 'Microsoft.Web/serverFarms',
            'event': 'write'},

        'BatchWrite': {
            'resource_provider': 'Microsoft.Batch/batchAccounts',
            'event': 'write'},

        'CdnProfileWrite': {
            'resource_provider': 'Microsoft.Cdn/profiles',
            'event': 'write'},

        'CognitiveServiceWrite': {
            'resource_provider': 'Microsoft.CognitiveServices/account',
            'event': 'write'},

        'ContainerServiceWrite': {
            'resource_provider': 'Microsoft.ContainerService/managedClusters',
            'event': 'write'},

        'CosmosDbWrite': {
            'resource_provider': 'Microsoft.DocumentDB/databaseAccounts',
            'event': 'write'},

        'DataFactoryWrite': {
            'resource_provider': 'Microsoft.DataFactory/factories',
            'event': 'write'},

        'DataLakeWrite': {
            'resource_provider': 'Microsoft.DataLakeStore/accounts',
            'event': 'write'},

        'DiskWrite': {
            'resource_provider': 'Microsoft.Compute/disks',
            'event': 'write'},

        'IotHubWrite': {
            'resource_provider': 'Microsoft.Devices/IotHubs',
            'event': 'write'},

        'KeyVaultWrite': {
            'resource_provider': 'Microsoft.KeyVault/vaults',
            'event': 'write'},

        'LoadBalancerWrite': {
            'resource_provider': 'Microsoft.Network/loadBalancers',
            'event': 'write'},

        'NetworkInterfaceWrite': {
            'resource_provider': 'Microsoft.Network/networkInterfaces',
            'event': 'write'},

        'NetworkSecurityGroupWrite': {
            'resource_provider': 'Microsoft.Network/networkSecurityGroups',
            'event': 'write'},

        'PublicIpWrite': {
            'resource_provider': 'Microsoft.Network/publicIPAddresses',
            'event': 'write'},

        'RedisWrite': {
            'resource_provider': 'Microsoft.Cache/Redis',
            'event': 'write'},

        'ResourceGroupWrite': {
            'resource_provider': 'Microsoft.Resources/subscriptions/resourceGroups',
            'event': 'write'},

        'SqlServerWrite': {
            'resource_provider': 'Microsoft.Sql/servers',
            'event': 'write'},

        'StorageWrite': {
            'resource_provider': 'Microsoft.Storage/storageAccounts',
            'event': 'write'},

        'VmWrite': {
            'resource_provider': 'Microsoft.Compute/virtualMachines',
            'event': 'write'},

        'VmssWrite': {
            'resource_provider': 'Microsoft.Compute/virtualMachineScaleSets',
            'event': 'write'},

        'VnetWrite': {
            'resource_provider': 'Microsoft.Network/virtualNetworks',
            'event': 'write'},

        'WebAppWrite': {
            'resource_provider': 'Microsoft.Web/sites',
            'event': 'write'}
    }

    @classmethod
    def get(cls, event):
        return cls.azure_events.get(event)

    @classmethod
    def get_event_operations(cls, events):
        event_operations = []
        for e in events:
            if isinstance(e, str):
                event = cls.get(e)
                event_operations.append('%s/%s' % (event['resource_provider'], event['event']))

            else:
                event_operations.append('%s/%s' % (e['resourceProvider'], e['event']))

        return event_operations


class AzureEventSubscription:

    @staticmethod
    def create(destination, name, subscription_id, session=None, event_filter=None):

        s = session or local_session(Session)
        event_filter = event_filter or EventSubscriptionFilter()

        event_info = EventSubscription(destination=destination, filter=event_filter)
        scope = '/subscriptions/%s' % subscription_id

        client = s.client('azure.mgmt.eventgrid.EventGridManagementClient')
        event_subscription = client.event_subscriptions.create_or_update(scope, name, event_info)
        return event_subscription.result()
