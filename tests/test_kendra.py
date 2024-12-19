from c7n.utils import local_session
from .common import BaseTest


class TestKendra(BaseTest):
    # write a test for adding and removing tags
    def test_kendra_tags(self):
        factory = self.replay_flight_data('test_kendra_tag')
        p = self.load_policy({
            'name': 'kendra-tag',
            'resource': 'aws.kendra',
            'actions': [
                {'type': 'tag',
                 'tags': {'TestTag': 'c7n'}},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('kendra')
        arn = f"arn:aws:kendra:us-east-1:123456789012:index/{resources[0]['Id']}"
        tags = client.list_tags_for_resource(ResourceARN=arn)["Tags"]
        self.assertEqual(tags[0]["Key"], "TestTag")

        p = self.load_policy({
            'name': 'kendra-untag',
            'resource': 'aws.kendra',
            'filters': [{"tag:TestTag": "c7n"}],
            'actions': [
                {'type': 'remove-tag',
                 'tags': ["TestTag"]},]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceARN=arn)["Tags"]
        self.assertEqual(len(tags), 0)

    def test_kendra_delete(self):
        factory = self.replay_flight_data('test_kendra_delete')
        p = self.load_policy({
            'name': 'kendra-delete',
            'resource': 'aws.kendra',
            'filters': [{'Name': 'c7n-test'}],
            'actions': ['delete']},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('kendra')
        index = client.describe_index(Id=resources[0]['Id'])
        self.assertEqual(index['Status'], 'DELETING')
