from .common import BaseTest

class TestRDSParameterGroupFilter(BaseTest):

    PARAMGROUP_PARAMETER_FILTER_TEST_CASES = [
        # filter_struct, test_func, err_message

        (
            {"key": "require_secure_transport", "op": "eq", "value": "ON"},
            lambda r: r == "ON",
            "require_secure_transport should be ON",
        ),
        (
            {"key": "tls_version", "op": "eq", "value": "TLSv1.2"},
            lambda r: r == "TLSv1.2",
            "tls_version should be TLSv1.2",
        ),
    ]

    def test_param_value_cases(self):
        session_factory = self.replay_flight_data('test_rdsclusterparamgroup_filter')
        policy = self.load_policy(
            {'name': 'rds-aurora-encr-in-transit', 'resource': 'rds-cluster'},
            session_factory=session_factory,
        )

        resources = policy.resource_manager.resources()
        print("Number of resources found: {}".format(len(resources)))
        self.assertEqual(len(resources), 2)

        for testcase in self.PARAMGROUP_PARAMETER_FILTER_TEST_CASES:
            fdata, assertion, err_msg = testcase
            f = policy.resource_manager.filter_registry.get("db-cluster-parameter")(
                fdata, policy.resource_manager
            )
            print('TEST CASE: {}'.format(fdata))
            f_resources = f.process(resources)
            print('Assert check : {}'.format(f_resources))

            if not assertion(f_resources):
               print(len(f_resources), fdata, assertion)
               self.fail(err_msg)