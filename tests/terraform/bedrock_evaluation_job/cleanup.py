#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import argparse
import time

import boto3
from botocore.exceptions import ClientError


TERMINAL_STATES = {"Completed", "Failed", "Stopped"}


def get_job(client, job_identifier):
    try:
        return client.get_evaluation_job(jobIdentifier=job_identifier)
    except client.exceptions.ResourceNotFoundException:
        return None


def find_job_arn(client, job_name):
    paginator = client.get_paginator("list_evaluation_jobs")
    for page in paginator.paginate(nameContains=job_name):
        for job in page["jobSummaries"]:
            if job["jobName"] == job_name:
                return job["jobArn"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Delete the ephemeral Bedrock evaluation job")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    client = boto3.client("bedrock", region_name=args.region)
    job_arn = find_job_arn(client, args.job_name)
    if job_arn is None:
        return
    job = get_job(client, job_arn)

    if job["status"] not in TERMINAL_STATES:
        try:
            client.stop_evaluation_job(jobIdentifier=job_arn)
        except client.exceptions.ConflictException:
            pass

    deadline = time.monotonic() + args.timeout
    while job and job["status"] not in TERMINAL_STATES:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {args.job_name} to stop")
        time.sleep(15)
        job = get_job(client, job_arn)

    if job is None:
        return

    try:
        response = client.batch_delete_evaluation_job(jobIdentifiers=[job_arn])
    except ClientError as error:
        raise RuntimeError(f"Unable to delete {args.job_name}") from error

    if response.get("errors"):
        raise RuntimeError(f"Unable to delete {args.job_name}: {response['errors']}")


if __name__ == "__main__":
    main()
