from .core import EventAction
from c7n import utils
from c7n.manager import resources
from c7n.version import version as VERSION


class LambdaInvoke(EventAction):
    """ Invoke an arbitrary lambda

    serialized invocation parameters

     - resources / collection of resources
     - policy / policy that is invoke the lambda
     - action / action that is invoking the lambda
     - event / cloud trail event if any
     - version / version of custodian invoking the lambda

    We automatically batch into sets of 250 for invocation,
    We try to utilize async invocation by default, this imposes
    some greater size limits of 128kb which means we batch
    invoke.

    Example::

     - type: invoke-lambda
       function: my-function
    """
    schema_alias = True
    schema = {
        'type': 'object',
        'required': ['type', 'function'],
        'properties': {
            'type': {'enum': ['invoke-lambda']},
            'function': {'type': 'string'},
            'async': {'type': 'boolean'},
            'qualifier': {'type': 'string'},
            'batch_size': {'type': 'integer'}
        }
    }

    def get_permissions(self):
        if self.data.get('async', True):
            return ('lambda:InvokeAsync',)
        return ('lambda:Invoke',)

    permissions = ('lambda:InvokeFunction',)

    def process(self, resources, event=None):
        client = utils.local_session(
            self.manager.session_factory).client('lambda')

        params = dict(FunctionName=self.data['function'])
        if self.data.get('qualifier'):
            params['Qualifier'] = self.data['Qualifier']

        if self.data.get('async', True):
            params['InvocationType'] = 'Event'

        payload = {
            'version': VERSION,
            'event': event,
            'action': self.data,
            'policy': self.manager.data}

        results = []
        for resource_set in utils.chunks(resources, self.data.get('batch_size', 250)):
            payload['resources'] = resource_set
            params['Payload'] = utils.dumps(payload)
            result = client.invoke(**params)
            result['Payload'] = result['Payload'].read()
            if isinstance(result['Payload'], bytes):
                result['Payload'] = result['Payload'].decode('utf-8')
            results.append(result)
        return results


def register_action_invoke_lambda(registry, _):
    for resource in registry.keys():
        klass = registry.get(resource)
        klass.action_registry.register('invoke-lambda', LambdaInvoke)


resources.subscribe(resources.EVENT_FINAL, register_action_invoke_lambda)
