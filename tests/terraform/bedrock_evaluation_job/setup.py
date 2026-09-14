#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import argparse
import json

import boto3


def restore_role_account(role_arn, account_id):
    parts = role_arn.split(':', 5)
    if len(parts) != 6 or parts[0:3] != ['arn', 'aws', 'iam']:
        raise ValueError(f"Invalid IAM role ARN: {role_arn}")
    parts[4] = account_id
    return ':'.join(parts)


def main():
    parser = argparse.ArgumentParser(description="Create the ephemeral Bedrock evaluation job")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--model-arn", required=True)
    parser.add_argument("--output-s3-uri", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = restore_role_account(args.role_arn, account_id)
    client = session.client("bedrock")
    response = client.create_evaluation_job(
        jobName=args.job_name,
        jobDescription="Cloud Custodian Bedrock evaluation job integration test",
        roleArn=role_arn,
        applicationType="ModelEvaluation",
        evaluationConfig={
            "automated": {
                "datasetMetricConfigs": [
                    {
                        "taskType": "QuestionAndAnswer",
                        "dataset": {"name": "Builtin.BoolQ"},
                        "metricNames": ["Builtin.Accuracy"],
                    }
                ]
            }
        },
        inferenceConfig={
            "models": [
                {
                    "bedrockModel": {
                        "modelIdentifier": args.model_arn,
                        "inferenceParams": json.dumps(
                            {
                                "inferenceConfig": {
                                    "maxTokens": 512,
                                    "temperature": 0.0,
                                }
                            }
                        ),
                    }
                }
            ]
        },
        outputDataConfig={"s3Uri": args.output_s3_uri},
        jobTags=[
            {"key": "Environment", "value": "test"},
            {"key": "Owner", "value": "c7n"},
        ],
    )
    print(response["jobArn"])


if __name__ == "__main__":
    main()
