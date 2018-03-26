import importlib

from azure.cli.core.cloud import AZURE_PUBLIC_CLOUD
from azure.cli.core._profile import Profile


class Session(object):

    def __init__(self):
        (self.credentials,
         self.subscription_id,
         self.tenant_id) = Profile().get_login_credentials(
            resource=AZURE_PUBLIC_CLOUD.endpoints.active_directory_resource_id)

    def client(self, client):
        service_name, client_name = client.rsplit('.', 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)
        return klass(self.credentials, self.subscription_id)


