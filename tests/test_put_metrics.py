# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import yaml_load
from .common import BaseTest
import logging
from pprint import pformat

logger = logging.getLogger(name="c7n.tests")


class PutMetricsTest(BaseTest):
    record = False
    EXAMPLE_EC2_POLICY = """
            policies:
              - name: track-attached-ebs
                resource: ec2
                comment: |
                  Put the count of the number of EBS attached disks to an instance
                #filters:
                #  - Name: tracked-ec2-instance
                actions:
                  - type: put-metric
                    key: BlockDeviceMappings[].DeviceName
                    namespace: Usage Metrics
                    metric_name: Attached Disks
                    dimensions:
                      - { a: b }
                    op: distinct_count
        """
    EXAMPLE_S3_POLICY = """
            policies:
              - name: bucket-count
                resource: s3
                comment: |
                  Count all the buckets!
                #filters:
                #    - Name: passthru
                #      type: value
                #      key: Name
                #      value: 0
                actions:
                  - type: put-metric
                    key: Name
                    namespace: Usage Metrics
                    metric_name: S3 Buckets
                    op: count
        """

    def _get_test_policy(self, name, yaml_doc, record=False):
        if record:
            logger.warn("TestPutMetrics is RECORDING")
            session_factory = self.record_flight_data("test_cw_put_metrics_" + name)
        else:
            logger.debug("TestPutMetrics is replaying")
            session_factory = self.replay_flight_data("test_cw_put_metrics_" + name)

        policy = self.load_policy(
            yaml_load(yaml_doc)["policies"][0], session_factory=session_factory
        )

        return policy

    def _test_putmetrics_s3(self):
        """ This test fails when replaying flight data due to an issue with placebo.
        """
        policy = self._get_test_policy(
            name="s3test", yaml_doc=self.EXAMPLE_S3_POLICY, record=self.record
        )
        resources = policy.run()

        logger.debug(
            "these are the results from the policy, assumed to be resources that were processed"
        )
        logger.debug(pformat(resources))
        self.assertGreaterEqual(
            len(resources), 1, "PutMetricsTest appears to have processed 0 resources."
        )

    def test_putmetrics_ec2(self):
        policy = self._get_test_policy(
            name="ec2test", yaml_doc=self.EXAMPLE_EC2_POLICY, record=self.record
        )
        resources = policy.run()
        logger.debug(
            "these are the results from the policy, assumed to be resources that were processed"
        )
        logger.debug(pformat(resources))
        self.assertGreaterEqual(
            len(resources),
            1,
            "PutMetricsTest appears to have processed 0 resources. "
            "Are there any running ec2 instances?",
        )

    def test_putmetrics_permissions(self):
        from c7n.actions import PutMetric

        self.assertTrue("cloudwatch:PutMetricData" in PutMetric.permissions)
        pma = PutMetric()
        self.assertTrue("cloudwatch:PutMetricData" in pma.get_permissions())

    def test_putmetrics_schema(self):
        import jsonschema
        from c7n.actions import PutMetric

        data = yaml_load(self.EXAMPLE_EC2_POLICY)
        action_schema = PutMetric.schema
        res = jsonschema.validate(data["policies"][0]["actions"][0], action_schema)
        self.assertIsNone(res, "PutMetric.schema failed to validate.")
