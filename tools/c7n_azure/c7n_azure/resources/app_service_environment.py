from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register("app-service-environment")
class AppServiceEnvironment(ArmResourceManager):
    """App Service Environment

    :example:

    This policy will find all App Service Environment that are still not ready

    .. code-block:: yaml

        policies:
          - name: app-service-environment-not-ready
            resource: azure.app-service-environment
            filters:
              - type: value
                key: properties.provisioningState
                value: InProgress
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ["Compute", "Web"]
        service = "azure.mgmt.web"
        client = "WebSiteManagementClient"
        enum_spec = ("app_service_environments", "list", None)
        default_report_fields = (
            "name",
            "location",
            "resourceGroup",
            "kind",
            "properties.dnsSuffix"
        )
        resource_type = "Microsoft.Web/hostingEnvironments"
