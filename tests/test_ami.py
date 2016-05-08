
from common import BaseTest


class TestAMI(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_ami')
        p = self.load_policy({
            'name': 'test-ami',
            'resource': 'ami',
            'filters': [
                {'Name': 'LambdaCompiler'},
                {'type': 'image-age', 'days': 0.2}],
            'actions': ['deregister']
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
        
