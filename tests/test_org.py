import json

import boto3
import moto
import pytest

template_body = json.dumps(
    {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Resources": {"Queue": {"Type": "AWS::SQS::Queue"}},
    }
)


@pytest.fixture(scope="function")
def org_tree(request):

    with moto.mock_organizations():
        client = boto3.client("organizations")
        org = client.create_organization(FeatureSet="ALL")["Organization"]
        root = client.list_roots()["Roots"][0]

        dept_a = client.create_organizational_unit(ParentId=org["Id"], Name="DeptA")[
            "OrganizationalUnit"
        ]
        dept_b = client.create_organizational_unit(ParentId=org["Id"], Name="DeptB")[
            "OrganizationalUnit"
        ]
        group_c = client.create_organizational_unit(
            ParentId=dept_a["Id"], Name="GroupC"
        )["OrganizationalUnit"]

        account_a = client.create_account(
            Email="a@example.com",
            AccountName="a",
            Tags=[{"Key": "Owner", "Value": "alice"}],
        )["CreateAccountStatus"]

        client.move_account(
            AccountId=account_a["AccountId"],
            SourceParentId=root["Id"],
            DestinationParentId=dept_a["Id"],
        )

        account_b = client.create_account(
            Email="b@example.com",
            AccountName="b",
            Tags=[{"Key": "Owner", "Value": "bob"}],
        )["CreateAccountStatus"]

        client.move_account(
            AccountId=account_b["AccountId"],
            SourceParentId=root["Id"],
            DestinationParentId=dept_b["Id"],
        )

        account_c = client.create_account(
            Email="b@example.com",
            AccountName="c",
            Tags=[{"Key": "Owner", "Value": "eve"}],
        )["CreateAccountStatus"]

        client.move_account(
            AccountId=account_c["AccountId"],
            SourceParentId=root["Id"],
            DestinationParentId=group_c["Id"],
        )

        yield dict(
            org=org,
            dept_a=dept_a,
            dept_b=dept_b,
            group_c=group_c,
            account_a=account_a,
            account_b=account_b,
            account_c=account_c,
            root=root,
        )


def test_org_account_ou_filter(test, org_tree):
    p = test.load_policy(
        {
            "name": "accounts",
            "resource": "aws.org-account",
            "filters": [{"type": "ou", "units": [org_tree["dept_a"]["Id"]]}],
        }
    )
    resources = p.run()
    assert {r["Id"] for r in resources} == {
        org_tree["account_a"]["AccountId"],
        org_tree["account_c"]["AccountId"],
    }


def test_org_account_moto(test, org_tree):
    p = test.load_policy(
        {
            "name": "accounts",
            "resource": "aws.org-account",
        },
    )
    resources = p.run()
    assert len(resources) == 4
    p = test.load_policy(
        {
            "name": "accounts",
            "resource": "aws.org-account",
            "filters": [{"tag:Owner": "eve"}],
        },
    )
    resources = p.run()
    assert len(resources) == 1


@moto.mock_cloudformation
def test_org_account_filter_cfn_absent(test):
    p = test.load_policy(
        {
            "name": "org-cfn-check",
            "resource": "aws.org-account",
            "filters": [{"type": "cfn-stack", "stack_names": ["bob"]}],
        }
    )
    cfn_stack = p.resource_manager.filters[0]
    result = cfn_stack.process_account_region(
        {"Id": "123", "Name": "test-account"}, "us-east-1", boto3.Session()
    )
    assert result is True


@moto.mock_cloudformation
def test_org_account_filter_cfn_present(test):
    p = test.load_policy(
        {
            "name": "org-cfn-check",
            "resource": "aws.org-account",
            "filters": [
                {
                    "type": "cfn-stack",
                    "status": ["CREATE_COMPLETE", "UPDATE_COMPLETE"],
                    "stack_names": ["bob"],
                }
            ],
        }
    )
    cfn_stack = p.resource_manager.filters[0]
    s = boto3.Session()
    cfn = s.client("cloudformation")
    cfn.create_stack(StackName="bob", TemplateBody=template_body)
    result = cfn_stack.process_account_region(
        {"Id": "123", "Name": "test-account"}, "us-east-1", s
    )
    assert result is False
