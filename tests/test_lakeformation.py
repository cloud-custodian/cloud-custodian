from .common import BaseTest


class LakeFormationTest(BaseTest):

    def test_lakeformation_value_filter(self):
        factory = self.replay_flight_data("test_lakeformation_list_resources")
        p = self.load_policy({
            'name': 'list_lakeformation_resources',
            'resource': 'lakeformation',
            "filters": [{"RoleArn": "present"}], },
            session_factory=factory)
        resources = p.run()
        print(resources)
        self.assertEqual(len(resources), 2)
