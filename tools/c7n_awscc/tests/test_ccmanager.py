# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_awscc.manager import initialize_resource, get_update_schema


def test_init_resource_access_analyzer():
    data = initialize_resource("eks_cluster")
    assert "EksCluster" in data
    klass = data["EksCluster"]
    assert klass.permissions == ["eks:DescribeCluster", "eks:ListClusters"]


def test_update_schema():
    klass = initialize_resource("sqs_queue")["SqsQueue"]
    update_schema = get_update_schema(klass.schema, "sqs_queue")
    assert set(update_schema["properties"]) >= {
        "ContentBasedDeduplication",
        "DeduplicationScope",
        "DelaySeconds",
        "FifoThroughputLimit",
        "KmsDataKeyReusePeriodSeconds",
        "KmsMasterKeyId",
        "MaximumMessageSize",
        "MessageRetentionPeriod",
        "ReceiveMessageWaitTimeSeconds",
        "RedriveAllowPolicy",
        "RedrivePolicy",
        "SqsManagedSseEnabled",
        "Tags",
        "VisibilityTimeout",
        "type",
    }
