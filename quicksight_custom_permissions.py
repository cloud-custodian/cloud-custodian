#!/usr/bin/env python3


import argparse
import boto3
from botocore.exceptions import ClientError

PERMISSIONS_NAME = "c7n-test-permissions"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--user-name", required=True,
                        help="e.g. AWSReservedSSO_.../eah523")
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    client = boto3.client("quicksight", region_name=args.region)

    try:
        # QuickSight capabilities are deny-only (CapabilityState enum == DENY).
        # Only the listed capabilities are denied; everything else is allowed.
        resp = client.create_custom_permissions(
            AwsAccountId=args.account_id,
            CustomPermissionsName=PERMISSIONS_NAME,
            Capabilities={"SubscribeDashboardEmailReports": "DENY"},
            Tags=[{"Key": "managed-by", "Value": "c7n-test"}],
        )
        print(f"Created: {resp['Arn']} (status {resp['Status']})")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceExistsException":
            print(f"'{PERMISSIONS_NAME}' already exists, reusing it.")
        else:
            raise

    resp = client.update_user_custom_permission(
        AwsAccountId=args.account_id,
        Namespace=args.namespace,
        UserName=args.user_name,
        CustomPermissionsName=PERMISSIONS_NAME,
    )
    print(f"Assigned '{PERMISSIONS_NAME}' to {args.user_name} "
        f"(status {resp['Status']})")


if __name__ == "__main__":
    main()
