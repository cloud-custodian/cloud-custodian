"""
Fetch and get the latest copy of the cfn schema catalog to include in the packaged
wheel.

https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-type-schemas.html

"""

import json
from io import BytesIO
from pathlib import Path
import zipfile
import requests

# we use this to fetch the available python sdk service names.
# boto is listed as a build dependency.
import boto3

try:
    from hatchling.plugin import hookimpl
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface

    class CloudDataBuild(BuildHookInterface):

        PLUGIN_NAME = "CloudServiceData"

        def initialize(self, version, build_data):
            build({})
            build_data["artifacts"].append("data/*.json")

    @hookimpl
    def hatch_register_build_hook():
        return CloudDataBuild

except ImportError:
    pass


SCHEMA_URL = "https://schema.cloudformation.us-east-1.amazonaws.com/CloudformationSchema.zip"


def fake_session():
    session = boto3.Session(  # nosec nosemgrep
        region_name="us-east-1",
        aws_access_key_id="never",
        aws_secret_access_key="found",
    )
    return session


ServiceMap = {
    "acmpca": "acm-pca",
    "amazonmq": "mq",
    "applicationinsights": "application-insights",
    "applicationautoscaling": "application-autoscaling",
    "aps": "amp",
    "backupgateway": "backup-gateway",
    "cassandra": "keyspaces",
    "certificatemanager": "acm",
    "codestarconnections": "codestar-connections",
    "codestarnotification": "codestar-notifications",
    "cognito": "cognito-identity",
    "customerprofiles": "customer-profiles",
    "devopsguru": "devops-guru",
    "elasticloadbalancingv2": "elbv2",
    "elasticloadbalancing": "elb",
    "emrserverless": "emr-serverless",
    "emrcontainers": "emr-containers",
    "eventschemas": "schemas",
    "elasticsearch": "es",
    "inspectorv2": "inspector2",
    "iotcoredeviceadvisor": "iotdeviceadvisor",
    "kinesisfirehose": "kinesis-firehose",
    "lex": "lexv2-models",
    "licensemanager": "license-manager",
    "msk": "kafka",
    "networkfirewall": "network-firewall",
    "nimblestudio": "nimble",
    "opensearchservice": "es",
    "resourcegroups": "resource-groups",
    "redshiftserverless": "redshift-serverless",
    "route53recoverycontrol": "route53-recovery-control-config",
    "route53recoveryreadiness": "route53-recovery-readiness",
    "s3objectlambda": "s3control",
    "servicecatalogappregistry": "servicecatalog-appregistry",
    "ssmcontacts": "ssm-contacts",
    "ssmincidents": "ssm-incidents",
    "vpclattice": "vpc-lattice",
    "wafregional": "waf-regional",
    "AWS::Timestream::Database": "timestream-write",
    "AWS::Timestream::ScheduledQuery": "timestream-query",
    "AWS::Timestream::Table": "timestream-write",
}


def build_index(data_dir):
    index_path = data_dir / "index.json"
    index_data = {"resources": {}, "augment": {}}
    all_services = fake_session().get_available_services()

    for path in sorted(data_dir.rglob("*.json")):
        if path.name == "index.json":
            continue

        rdata = json.loads(path.read_text(encoding="utf8"))

        if "handlers" not in rdata:
            print("awscc - resource has no handlers %s" % (rdata["typeName"]))
            continue

        service = path.stem.split("_")[1]

        if service not in all_services:
            boto_service = ServiceMap.get(service)
            if boto_service is None:
                boto_service = ServiceMap.get(rdata["typeName"])
        else:
            boto_service = service
        if not boto_service:
            print("awscc - service not found %s %s" % (rdata["typeName"], service))
            continue

        raugment = index_data["augment"].setdefault(rdata["typeName"], {})
        raugment["service"] = boto_service

        rname = path.stem.split("_", 1)[-1]
        raugment["type"] = rname
        class_name = "".join([s.title() for s in path.stem.split("_")[1:]])
        index_data["resources"]["awscc.%s" % rname] = "c7n_awscc.resources.%s.%s" % (
            path.stem.split("_", 1)[-1],
            class_name,
        )

    index_path.write_text(json.dumps(index_data, indent=2))


def build(setup_kwargs):
    data_dir = Path("c7n_awscc") / "data"
    data_dir.mkdir(exist_ok=True)

    response = requests.get(SCHEMA_URL)

    zipf = zipfile.ZipFile(BytesIO(response.content))
    for f in zipf.namelist():
        name = f.replace("-", "_")
        (data_dir / name).write_text(zipf.read(f).decode("utf8"), encoding="utf8")

    print("awscc - downloaded %d resource types" % (len(zipf.namelist())))
    build_index(data_dir)

    return setup_kwargs


if __name__ == "__main__":
    build({})
