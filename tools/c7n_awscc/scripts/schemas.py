# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import click
import boto3
import json
import os


from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def process_resource_schema(cfn, rtype):
    return cfn.describe_type(TypeName=rtype, Type="RESOURCE")


def process_resource_list(control, rinfo):
    control.list_resources(TypeName=rinfo["typeName"])
    return True


def extract_custodian(rdata, c7n_resource, raugment):
    # extract any custodian metadata if we have the same
    # resource in both providers.
    raugment["c7n_type"] = "aws.%s" % c7n_resource.type


ServiceMap = {
    "acmpca": "acm-pca",
    "applicationinsights": "application-insights",
    "aps": "amp",
    # cassandra : no management api
    "cassandra": "keyspaces",
    "certificatemanager": "acm",
    # chatbot: no management api
    "codestarconnections": "codestar-connections",
    "codestarnotification": "codestar-notifications",
    "customerprofiles": "customer-profiles",
    "devopsguru": "devops-guru",
    "elasticloadbalancingv2": "elbv2",
    "emrcontainers": "emr-containers",
    "eventschemas": "schemas",
    "inspectorv2": "inspector2",
    "iotcoredeviceadvisor": "iotdeviceadvisor",
    "kinesisfirehose": "kinesis-firehose",
    "lex": "lexv2-models",
    "licensemanager": "license-manager",
    "networkfirewall": "network-firewall",
    "nimblestudio": "nimble",
    "opensearchservice": "es",
    "resourcegroups": "resource-groups",
    "route53recoverycontrol": "route53-recovery-control-config",
    "route53recoveryreadiness": "route53-recovery-readiness",
    "s3objectlambda": "s3control",
    "servicecatalogappregistry": "servicecatalog-appregistry",
    "ssmcontacts": "ssm-contacts",
    "ssmincidents": "ssm-incidents",
    "aws_timestream_database": "timestream-write",
    "aws_timestream_scheduledquery": "timestream-query",
    "aws_timestream_table": "timestream-write",
}


@click.group()
def cli():
    """ """
    os.environ["AWS_RETRY_MODE"] = "adaptive"
    os.environ["AWS_MAX_ATTEMPTS"] = "6"


@cli.command()
@click.option("-o", "--index", required=True, type=click.Path())
@click.option("-d", "--schema-dir", required=True, type=click.Path())
def gen_index(index, schema_dir):
    index_path = Path(index)
    schema_dir = Path(schema_dir)

    from c7n.resources import load_resources

    load_resources(("aws.*"))
    from c7n.resources.aws import AWS

    index_data = {"resources": {}, "augment": {}}

    all_services = boto3.Session().get_available_services()
    cfn_c7n_map = {}

    for rname, rtype in AWS.resources.items():
        if not rtype.resource_type.cfn_type:
            continue
        cfn_c7n_map[rtype.resource_type.cfn_type] = rtype

    for path in sorted(schema_dir.rglob("*.json")):
        if path.name == "index.json":
            continue
        service = path.stem.split("_")[1]
        rdata = json.loads(path.read_text())

        raugment = index_data["augment"].setdefault(rdata["typeName"], {})
        if service not in all_services:
            service = ServiceMap.get(service)
        raugment["service"] = service

        rname = path.stem.split("_", 1)[-1]
        raugment["type"] = rname

        c7n_resource = cfn_c7n_map.get(rdata["typeName"])
        if c7n_resource:
            extract_custodian(rdata, c7n_resource, raugment)

        class_name = "".join([s.title() for s in path.stem.split("_")[1:]])
        index_data["resources"]["awscc.%s" % rname] = "c7n_awscc.resources.%s.%s" % (
            path.stem.split("_", 1)[-1],
            class_name,
        )

    index_path.write_text(json.dumps(index_data, indent=2))


@cli.command()
@click.option("-d", "--schema-dir", required=True, type=click.Path())
def check_list(schema_dir):
    sdir = Path(str(schema_dir))
    control = boto3.client("cloudcontrol")
    with ThreadPoolExecutor(max_workers=4) as w:
        results = {}

        for p in sdir.rglob("*.json"):
            rinfo = json.loads(p.read_text())
            results[w.submit(process_resource_list, control, rinfo)] = (p, rinfo)

        for f in as_completed(results):
            p, rinfo = results[f]
            exc = f.exception()
            if exc:
                print(f"type: {rinfo['typeName']} error {exc}")
                p.unlink()
                continue


@cli.command()
@click.option("-o", "--output", required=True, type=click.Path())
def download(output):
    """download schema updates"""
    output = Path(str(output))

    cfn = boto3.client("cloudformation")
    resources = sorted(
        [
            t["TypeName"]
            for t in cfn.get_paginator("list_types")
            .paginate(
                Visibility="PUBLIC",
                Filters={"Category": "AWS_TYPES"},
                ProvisioningType="FULLY_MUTABLE",
                DeprecatedStatus="LIVE",
                Type="RESOURCE",
            )
            .build_full_result()["TypeSummaries"]
        ]
    )

    results = {}

    with ThreadPoolExecutor(max_workers=4) as w:
        results = {}
        for r in resources:
            results[w.submit(process_resource_schema, cfn, r)] = r

        for f in as_completed(results):
            r = results[f]
            if f.exception():
                print(f"type: {r} error {f.exception()}")
                continue
            fpath = output / ("%s.json" % r.replace("::", "_").lower())
            fpath.write_text(json.dumps(json.loads(f.result()["Schema"]), indent=2))
            print(f"downloaded {r}")


if __name__ == "__main__":
    try:
        cli()
    except Exception:
        import traceback, sys, pdb

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
