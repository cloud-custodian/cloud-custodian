# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.security import SecurityCenter

from c7n.utils import local_session
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, TypeInfo, ResourceManager

class SecurityContactsResourceManager(QueryResourceManager):

    # The SecurityCenter client takes an "asc_location" parameter, and the
    # documentation[^1] points out that this can come from the locations
    # list (elsewhere there are references to using a subscription's
    # "home region" for asc_location).
    #
    # However, from peeking at the Azure CLI's code it looks like they
    # hardcode an arbitrary/common location[^2]. The initial pull request
    # adding Defender to the CLI[^3] mentions that the intention is to
    # remove asc_location from client creation and hide it from the user.
    #
    # Following the Azure CLI team's lead and hardcoding "centralus"
    # here seems reasonable.
    #
    # [^1]: https://azuresdkdocs.blob.core.windows.net/$web/python/azure-mgmt-security/1.0.0/azure.mgmt.security.html#azure.mgmt.security.SecurityCenter  # noqa
    # [^2]: https://github.com/Azure/azure-cli/blob/29767d75d850ddc1c24cc85bd46d861b61d77a47/src/azure-cli/azure/cli/command_modules/security/_client_factory.py#L11  # noqa
    # [^3]: https://github.com/Azure/azure-cli/pull/7917#discussion_r238458818  # noqa

    def get_client(self):
        session = local_session(self.session_factory)
        return SecurityCenter(session.get_credentials(), session.subscription_id, "centralus")

@resources.register("security-contacts")
class SecurityContacts(SecurityContactsResourceManager, metaclass=QueryMeta):
    """Get Default Security contact configurations for the subscription.
    .. code-block:: yaml
    policies:
        - name: mck-azure-security-ensure-send-email-notification-for-high-severity-alerts-is-enabled
        resource: azure.security-contacts
        filters:
            - name: default
            - properties.alertNotifications.state: "On"
    """

    # interior class that defines the metadata for resource
    class resource_type(TypeInfo):
        doc_groups = ['Security']

        id = 'subscriptionId'
        name = 'default'
        client = "SecurityCenter"
        filter_name = None
        service = "security"
        enum_spec = ("security_contacts", "list", None)
        resource_type = "Microsoft.Security"

