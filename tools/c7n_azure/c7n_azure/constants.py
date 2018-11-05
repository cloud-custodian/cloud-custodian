"""
Azure Functions
"""
# Docker version from https://hub.docker.com/r/microsoft/azure-functions/
FUNCTION_DOCKER_VERSION = 'DOCKER|mcr.microsoft.com/azure-functions/python:latest'
FUNCTION_EXT_VERSION = 'beta'
FUNCTION_EVENT_TRIGGER_MODE = 'azure-event-grid'
FUNCTION_TIME_TRIGGER_MODE = 'azure-periodic'
FUNCTION_KEY_URL = 'hostruntime/admin/host/systemkeys/_master?api-version=2018-02-01'

"""
Event Grid Mode
"""
EVENT_GRID_USER_NAME_JMES_PATH = \
    'data.claims."http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"'
EVENT_GRID_SP_NAME_JMES_PATH = 'data.claims.appid'
EVENT_GRID_PRINCIPAL_TYPE_JMES_PATH = 'data.authorization.evidence.principalType'

"""
Environment Variables
"""
ENV_TENANT_ID = 'AZURE_TENANT_ID'
ENV_CLIENT_ID = 'AZURE_CLIENT_ID'
ENV_SUB_ID = 'AZURE_SUBSCRIPTION_ID'
ENV_CLIENT_SECRET = 'AZURE_CLIENT_SECRET'

ENV_ACCESS_TOKEN = 'AZURE_ACCESS_TOKEN'

ENV_FUNCTION_TENANT_ID = 'AZURE_FUNCTION_TENANT_ID'
ENV_FUNCTION_CLIENT_ID = 'AZURE_FUNCTION_CLIENT_ID'
ENV_FUNCTION_SUB_ID = 'AZURE_FUNCTION_SUBSCRIPTION_ID'
ENV_FUNCTION_CLIENT_SECRET = 'AZURE_FUNCTION_CLIENT_SECRET'

# Allow disabling SSL cert validation (ex: custom domain for ASE functions)
ENV_CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION = 'CUSTODIAN_DISABLE_SSL_CERT_VERIFICATION'

"""
Authentication Resource
"""
RESOURCE_STORAGE = 'https://storage.azure.com/'

"""
Threading Variable
"""
DEFAULT_MAX_THREAD_WORKERS = 3
DEFAULT_CHUNK_SIZE = 20
