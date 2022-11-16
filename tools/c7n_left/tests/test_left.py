# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import json
import os
from unittest.mock import ANY

import pytest
from pathlib import Path

from click.testing import CliRunner

from c7n.config import Config
from c7n.resources import load_resources

try:
    from c7n_left import cli, utils, core
    from c7n_left.providers.terraform.provider import (
        TerraformProvider,
        TerraformResourceManager,
    )
    from c7n_left.providers.terraform.graph import Resolver

    LEFT_INSTALLED = True
except ImportError:
    pytest.skip(reason="c7n_left not installed", allow_module_level=True)
    LEFT_INSTALLED = False
else:
    load_resources(("terraform.*",))

cur_dir = Path(os.curdir).absolute()
terraform_dir = Path(__file__).parent.parent.parent.parent / "tests" / "terraform"
terraform_dir = terraform_dir.relative_to(cur_dir)


class ResultsReporter:
    def __init__(self):
        self.results = []

    def on_execution_started(self, policies):
        pass

    def on_execution_ended(self):
        pass

    def on_results(self, results):
        self.results.extend(results)


def run_policy(policy, terraform_dir, tmp_path):
    (tmp_path / "policies.json").write_text(
        json.dumps({"policies": [policy]}, indent=2)
    )
    config = Config.empty(policy_dir=tmp_path, source_dir=terraform_dir)
    policies = utils.load_policies(tmp_path, config)
    reporter = ResultsReporter()
    core.CollectionRunner(policies, config, reporter).run()
    return reporter.results


def test_load_policy(test):
    test.load_policy(
        {"name": "check1", "resource": "terraform.aws_s3_bucket"}, validate=True
    )
    test.load_policy(
        {"name": "check2", "resource": ["terraform.aws_s3_bucket"]}, validate=True
    )
    test.load_policy({"name": "check3", "resource": ["terraform.aws_*"]}, validate=True)


def test_load_policy_dir(tmp_path):
    write_output_test_policy(tmp_path)
    policies = utils.load_policies(tmp_path, Config.empty())
    assert len(policies) == 1


def test_graph_resolver():
    graph = TerraformProvider().parse(terraform_dir / "vpc_flow_logs")
    resolver = graph.build()

    log = list(graph.get_resources_by_type("aws_flow_log"))[0][1][0]
    iam_role = list(resolver.resolve_refs(log, ("aws_iam_role",)))[0]

    assert iam_role["name_prefix"] == "example"
    assert {r["__tfmeta"]["label"] for r in resolver.resolve_refs(log)} == set(
        ("aws_vpc", "aws_cloudwatch_log_group", "aws_iam_role")
    )


def test_resource_type_interface():
    rtype = TerraformResourceManager(None, {}).get_model()
    assert rtype.id == "id"


def test_graph_resolver_inner_block_ref():
    graph = TerraformProvider().parse(terraform_dir / "aws_code_build_vpc")
    resolver = graph.build()
    project = list(graph.get_resources_by_type("aws_codebuild_project"))[0][1][0]
    assert {r["__tfmeta"]["label"] for r in resolver.resolve_refs(project)} == set(
        ("aws_vpc", "aws_security_group", "aws_iam_role", "aws_subnet")
    )


def test_graph_resolver_id():
    resolver = Resolver()
    assert resolver.is_id_ref("4b3db3ec-98ad-4382-a460-d8e392d128b7") is True
    assert resolver.is_id_ref("a" * 36) is False


def test_traverse_multi_resource_multi_set(tmp_path):
    resources = run_policy(
        {
            "name": "check-link",
            "resource": "terraform.aws_s3_bucket",
            "filters": [
                {
                    "type": "traverse",
                    "resources": "aws_s3_bucket_ownership_controls",
                    "attrs": [
                        {
                            "type": "value",
                            "key": "rule.object_ownership",
                            "value": ["BucketOwnerPreferred", "BucketOwnerEnforced"],
                            "op": "in",
                        }
                    ],
                }
            ],
        },
        terraform_dir / "s3_ownership",
        tmp_path,
    )
    assert len(resources) == 2
    assert {r.resource.name for r in resources} == {
        "aws_s3_bucket.owner_enforced",
        "aws_s3_bucket.owner_preferred",
    }


def test_traverse_filter_not_found(tmp_path):
    resources = run_policy(
        {
            "name": "check-link",
            "resource": "terraform.aws_codebuild_project",
            "filters": [
                {
                    "type": "traverse",
                    "resources": ["aws_security_group", "aws_vpc"],
                    "attrs": [{"tag:Env": "Prod"}],
                }
            ],
        },
        terraform_dir / "aws_code_build_vpc",
        tmp_path,
    )
    assert len(resources) == 0


def test_traverse_filter_not_found_matches(tmp_path):
    resources = run_policy(
        {
            "name": "check-link",
            "resource": "terraform.aws_codebuild_project",
            "filters": [
                {
                    "type": "traverse",
                    "resources": ["aws_security_group", "aws_vpc"],
                    "count": 0,
                    "attrs": [{"tag:Env": "Prod"}],
                }
            ],
        },
        terraform_dir / "aws_code_build_vpc",
        tmp_path,
    )
    assert len(resources) == 1


def test_traverse_filter_multi_hop(tmp_path):
    resources = run_policy(
        {
            "name": "check-link",
            "resource": "terraform.aws_codebuild_project",
            "filters": [
                {
                    "type": "traverse",
                    "resources": ["aws_security_group", "aws_vpc"],
                    "count": 1,
                    "attrs": [{"tag:Env": "Dev"}],
                }
            ],
        },
        terraform_dir / "aws_code_build_vpc",
        tmp_path,
    )
    assert len(resources) == 1


def test_boolean(tmp_path):
    resources = run_policy(
        {
            "name": "check-link",
            "resource": "terraform.aws_s3_bucket",
            "filters": [{"not": [{"server_side_encryption_configuration": "present"}]}],
        },
        terraform_dir / "aws_s3_encryption_audit",
        tmp_path,
    )
    assert len(resources) == 1
    assert resources[0].resource["bucket"] == "c7n-aws-s3-encryption-audit-test-c"


def test_provider_parse():
    graph = TerraformProvider().parse(terraform_dir / "ec2_stop_protection_disabled")
    resource_types = list(graph.get_resources_by_type("aws_subnet"))
    rtype, resources = resource_types.pop()
    assert rtype == "aws_subnet"
    assert resources[0]["__tfmeta"] == {
        "type": "resource",
        "label": "aws_subnet",
        "path": "aws_subnet.example",
        "filename": "network.tf",
        "line_start": 5,
        "line_end": 8,
        "src_dir": Path("tests") / "terraform" / "ec2_stop_protection_disabled",
    }


def test_multi_resource_policy(tmp_path):
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "policies": [
                    {
                        "name": "check-wild",
                        "resource": "terraform.aws_*",
                    }
                ]
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_lambda_check_permissions"),
            "-o",
            "json",
            "--output-file",
            str(tmp_path / "output.json"),
        ],
    )
    assert result.exit_code == 1
    data = json.loads((tmp_path / "output.json").read_text())
    assert len(data["results"]) == 2


def write_output_test_policy(tmp_path):
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "policies": [
                    {
                        "name": "check-bucket",
                        "resource": "terraform.aws_s3_bucket",
                        "description": "a description",
                        "filters": [{"server_side_encryption_configuration": "absent"}],
                    }
                ]
            }
        )
    )


def test_cli_no_policies(tmp_path, caplog):
    runner = CliRunner()
    runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
        ],
    )
    assert caplog.record_tuples == [("c7n.iac", 30, "no policies found")]


def test_cli_output_rich(tmp_path):
    write_output_test_policy(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "cli",
        ],
    )
    assert result.exit_code == 1
    assert "Reason: a description\n" in result.output


def test_cli_output_github(tmp_path):
    write_output_test_policy(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "github",
        ],
    )
    assert result.exit_code == 1
    assert result.output == (
        "::error file=tests/terraform/aws_s3_encryption_audit/main.tf line=25 lineEnd=28"
        " title=terraform.aws_s3_bucket - policy:check-bucket::a description\n"
    )


def test_cli_output_json_query(tmp_path):
    write_output_test_policy(tmp_path)

    runner = CliRunner()
    runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "json",
            "--output-file",
            str(tmp_path / "output.json"),
            "--output-query",
            "[].file_path",
        ],
    )

    results = json.loads((tmp_path / "output.json").read_text())
    assert results == {
        "results": [
            "tests/terraform/aws_s3_encryption_audit/main.tf",
        ]
    }


def test_cli_output_json(tmp_path):
    write_output_test_policy(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "json",
            "--output-file",
            str(tmp_path / "output.json"),
        ],
    )
    assert result.exit_code == 1

    results = json.loads((tmp_path / "output.json").read_text())
    assert "results" in results
    assert results["results"] == [
        {
            "code_block": [
                [25, 'resource "aws_s3_bucket" "example_c" {'],
                [26, "  bucket = " '"c7n-aws-s3-encryption-audit-test-c"'],
                [27, '  acl    = "private"'],
                [28, "}"],
            ],
            "file_line_end": 28,
            "file_line_start": 25,
            "file_path": "tests/terraform/aws_s3_encryption_audit/main.tf",
            "policy": {
                "filters": [{"server_side_encryption_configuration": "absent"}],
                "mode": {"type": "terraform-source"},
                "name": "check-bucket",
                "resource": "terraform.aws_s3_bucket",
                "description": "a description",
            },
            "resource": {
                "__tfmeta": {
                    "filename": "main.tf",
                    "label": "aws_s3_bucket",
                    "line_end": 28,
                    "line_start": 25,
                    "path": "aws_s3_bucket.example_c",
                    "src_dir": "tests/terraform/aws_s3_encryption_audit",
                    "type": "resource",
                },
                "acl": "private",
                "bucket": "c7n-aws-s3-encryption-audit-test-c",
                "c7n:MatchedFilters": ["server_side_encryption_configuration"],
                "id": ANY,
            },
        }
    ]
