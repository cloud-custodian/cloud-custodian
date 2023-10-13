# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
ResourceMap = {
    "azure.advisor-recommendation": "c7n_azure.resources.advisor.AdvisorRecommendation",
    "azure.aks": "c7n_azure.resources.k8s_service.KubernetesService",
    "azure.app-insights": "c7n_azure.resources.appinsights.AzureAppInsights",
    "azure.open-shift": "c7n_azure.resources.open_shift.OpenShiftService",
    "azure.api-management": "c7n_azure.resources.apimanagement.ApiManagement",
    "azure.appserviceplan": "c7n_azure.resources.appserviceplan.AppServicePlan",
    "azure.application-gateway": "c7n_azure.resources.app_gateway.ApplicationGateway",
    "azure.armresource": "c7n_azure.resources.generic_arm_resource.GenericArmResource",
    "azure.bastion-host": "c7n_azure.resources.bastion_host.AzureBastionHost",
    "azure.batch": "c7n_azure.resources.batch.Batch",
    "azure.cdn-custom-domain": "c7n_azure.resources.cdn_custom_domain.CdnCustomDomain",
    "azure.cdn-endpoint": "c7n_azure.resources.cdn_endpoint.CdnEndpoint",
    "azure.cdnprofile": "c7n_azure.resources.cdn.CdnProfile",
    "azure.cognitiveservice": "c7n_azure.resources.cognitive_service.CognitiveService",
    "azure.container-group": "c7n_azure.resources.aci.ContainerGroup",
    "azure.containerregistry": "c7n_azure.resources.container_registry.ContainerRegistry",
    "azure.container-registry": "c7n_azure.resources.container_registry.ContainerRegistry",
    "azure.containerservice": "c7n_azure.resources.container_service.ContainerService",
    "azure.cosmosdb": "c7n_azure.resources.cosmos_db.CosmosDB",
    "azure.cosmosdb-collection": "c7n_azure.resources.cosmos_db.CosmosDBCollection",
    "azure.cosmosdb-database": "c7n_azure.resources.cosmos_db.CosmosDBDatabase",
    "azure.cost-management-export": "c7n_azure.resources.cost_management_export.CostManagementExport",  # noqa
    "azure.databricks": "c7n_azure.resources.databricks.Databricks",
    "azure.datafactory": "c7n_azure.resources.data_factory.DataFactory",
    "azure.datalake": "c7n_azure.resources.datalake_store.DataLakeStore",
    "azure.datalake-analytics": "c7n_azure.resources.datalake_analytics.DataLakeAnalytics",
    "azure.defender-autoprovisioning": "c7n_azure.resources.defender.DefenderAutoProvisioningSetting",  # noqa
    "azure.defender-pricing": "c7n_azure.resources.defender.DefenderPricing",
    "azure.defender-setting": "c7n_azure.resources.defender.DefenderSetting",
    "azure.disk": "c7n_azure.resources.disk.Disk",
    "azure.dnszone": "c7n_azure.resources.dns_zone.DnsZone",
    "azure.event-grid-domain": "c7n_azure.resources.event_grid_domain.EventGridDomain",
    "azure.event-grid-topic": "c7n_azure.resources.event_grid_topic.EventGridTopic",
    "azure.eventhub": "c7n_azure.resources.event_hub.EventHub",
    "azure.eventsubscription": "c7n_azure.resources.event_subscription.EventSubscription",
    "azure.front-door": "c7n_azure.resources.front_door.FrontDoor",
    "azure.front-door-policy": "c7n_azure.resources.front_door_policy.FrontDoorPolicy",
    "azure.hdinsight": "c7n_azure.resources.hdinsight.Hdinsight",
    "azure.host-pool": "c7n_azure.resources.host_pool.HostPool",
    "azure.image": "c7n_azure.resources.image.Image",
    "azure.iothub": "c7n_azure.resources.iot_hub.IoTHub",
    "azure.keyvault": "c7n_azure.resources.key_vault.KeyVault",
    "azure.keyvault-certificate": "c7n_azure.resources.key_vault_certificate.KeyVaultCertificate",
    "azure.keyvault-secret": "c7n_azure.resources.key_vault_secret.KeyVaultSecret",
    "azure.keyvault-key": "c7n_azure.resources.key_vault_keys.KeyVaultKeys",
    "azure.keyvault-keys": "c7n_azure.resources.key_vault_keys.KeyVaultKeys",
    "azure.loadbalancer": "c7n_azure.resources.load_balancer.LoadBalancer",
    "azure.logic-app-workflow": "c7n_azure.resources.logic_app.LogicAppWorkflow",
    "azure.mariadb": "c7n_azure.resources.mariadb.MariaDB",
    "azure.monitor-log-profile": "c7n_azure.resources.monitor_logprofile.MonitorLogprofile",
    "azure.mysql": "c7n_azure.resources.mysql.MySQL",
    "azure.mysql-flexibleserver": "c7n_azure.resources.mysql_flexibleserver.MySQLFlexibleServer",
    "azure.networkinterface": "c7n_azure.resources.network_interface.NetworkInterface",
    "azure.networksecuritygroup": "c7n_azure.resources.network_security_group.NetworkSecurityGroup",
    "azure.networkwatcher": "c7n_azure.resources.network_watcher.NetworkWatcher",
    "azure.policyassignments": "c7n_azure.resources.policy_assignments.PolicyAssignments",
    "azure.postgresql-database": "c7n_azure.resources.postgresql_database.PostgresqlDatabase",
    "azure.postgresql-server": "c7n_azure.resources.postgresql_server.PostgresqlServer",
    "azure.publicip": "c7n_azure.resources.public_ip.PublicIPAddress",
    "azure.recordset": "c7n_azure.resources.record_set.RecordSet",
    "azure.recovery-services": "c7n_azure.resources.recovery_services.RecoveryServices",
    "azure.redis": "c7n_azure.resources.redis.Redis",
    "azure.resourcegroup": "c7n_azure.resources.resourcegroup.ResourceGroup",
    "azure.roleassignment": "c7n_azure.resources.access_control.RoleAssignment",
    "azure.roledefinition": "c7n_azure.resources.access_control.RoleDefinition",
    "azure.routetable": "c7n_azure.resources.route_table.RouteTable",
    "azure.search": "c7n_azure.resources.search.SearchService",
    "azure.servicebus-namespace": "c7n_azure.resources.servicebus_namespace.ServiceBusNamespace",
    "azure.servicebus-namespace-networkrules": "c7n_azure.resources.servicebus_namespace_networkrules.ServiceBusNamespaceNetworkrules", # noqa
    "azure.servicebus-namespace-authrules": "c7n_azure.resources.servicebus_namespace_authrules.ServiceBusNamespaceAuthRules", # noqa
    "azure.service-fabric-cluster": "c7n_azure.resources.service_fabric.ServiceFabricCluster",
    "azure.service-fabric-cluster-managed": "c7n_azure.resources.service_fabric.ServiceFabricClusterManaged",  # noqa
    "azure.session-host": "c7n_azure.resources.session_host.SessionHost",
    "azure.spring-app": "c7n_azure.resources.spring.SpringApp",
    "azure.spring-service-instance": "c7n_azure.resources.spring.SpringServiceInstance",
    "azure.sql-database": "c7n_azure.resources.sqldatabase.SqlDatabase",
    "azure.sqldatabase": "c7n_azure.resources.sqldatabase.SqlDatabase",
    "azure.sql-server": "c7n_azure.resources.sqlserver.SqlServer",
    "azure.sqlserver": "c7n_azure.resources.sqlserver.SqlServer",
    "azure.storage": "c7n_azure.resources.storage.Storage",
    "azure.storage-container": "c7n_azure.resources.storage_container.StorageContainer",
    "azure.subscription": "c7n_azure.resources.subscription.Subscription",
    "azure.traffic-manager-profile": "c7n_azure.resources.traffic_manager.TrafficManagerProfile",
    "azure.vm": "c7n_azure.resources.vm.VirtualMachine",
    "azure.vmss": "c7n_azure.resources.vmss.VMScaleSet",
    "azure.vnet": "c7n_azure.resources.vnet.Vnet",
    "azure.webapp": "c7n_azure.resources.web_app.WebApp",
    "azure.defender-alert": "c7n_azure.resources.defender.DefenderAlertSettings",
    "azure.alert-logs": "c7n_azure.resources.alertlogs.AlertLogs",
}
