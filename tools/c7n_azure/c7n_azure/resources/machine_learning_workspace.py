from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager


@resources.register('machine-learning-workspace')
class MachineLearningWorkspace(QueryResourceManager):
    """Machine Learning Workspace Resource

    :example:

    Finds all Machine Learning Workspaces in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-machine-learning-workspaces
              resource: azure.machine-learning-workspace

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'AzureMachineLearningWorkspaces'
        enum_spec = ('workspaces', 'list_by_subscription', None)
