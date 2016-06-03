import logging

from c7n.query import ResourceQuery
from c7n.resources.vpc import InternetGateway

from common import BaseTest


class ResourceQueryTest(BaseTest):

    def test_query_filter(self):
        session_factory = self.replay_flight_data('test_query_filter')
        q = ResourceQuery(session_factory)
        resources = q.filter('aws.ec2.instance')
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['InstanceId'], 'i-9432cb49')

    def test_query_get(self):
        session_factory = self.replay_flight_data('test_query_get')
        q = ResourceQuery(session_factory)
        resources = q.get('aws.ec2.instance', ['i-9432cb49'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['InstanceId'], 'i-9432cb49')

    def test_query_model_get(self):
        session_factory = self.replay_flight_data('test_query_model')
        q = ResourceQuery(session_factory)
        resources = q.filter(InternetGateway.Meta)
        self.assertEqual(len(resources), 3)
        resources = q.get(InternetGateway.Meta, ['igw-3d9e3d56'])
        self.assertEqual(len(resources), 1)


class QueryResourceManagerTest(BaseTest):

    def test_registries(self):
        self.assertTrue(InternetGateway.filter_registry)
        self.assertTrue(InternetGateway.action_registry)

    def test_resources(self):
        session_factory = self.replay_flight_data('test_query_manager')
        p = self.load_policy(
            {'name': 'igw-check',
             'resource': 'internet-gateway',
             'filters': [{
                 'InternetGatewayId': 'igw-5bce113e'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
        output = self.capture_logging(
            name=p.resource_manager.log.name, level=logging.DEBUG)
        p.run()
        self.assertTrue("Using cached internet-gateway: 3", output.getvalue())
        
    def test_get_resources(self):
        session_factory = self.replay_flight_data('test_query_manager_get')
        p = self.load_policy(
            {'name': 'igw-check',
             'resource': 'internet-gateway'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(['igw-5bce113e'])
        self.assertEqual(len(resources), 1)
        resources = p.resource_manager.get_resources(['igw-5bce113f'])
        self.assertEqual(resources, [])
    
             
            
