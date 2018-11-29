# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import datetime
from dateutil.tz import tzutc

import hashlib
import jmespath
import json

from .core import BaseAction
from c7n.utils import type_schema, local_session, chunks

from c7n.resources.ec2 import EC2
from c7n.resources.s3 import S3, get_region
from c7n.version import version


FindingTypes = {
    "Software and Configuration Checks": [
        "Vulnerabilities",
        "Vulnerabilities/CVE",
        "AWS Security Best Practices",
        "AWS Security Best Practices/Network Reachability",
        "Industry and Regulatory Standards",
        "Industry and Regulatory Standards/CIS Host Hardening Benchmarks",
        "Industry and Regulatory Standards/CIS AWS Foundations Benchmark",
        "Industry and Regulatory Standards/PCI-DSS Controls",
        "Industry and Regulatory Standards/Cloud Security Alliance Controls",
        "Industry and Regulatory Standards/ISO 90001 Controls",
        "Industry and Regulatory Standards/ISO 27001 Controls",
        "Industry and Regulatory Standards/ISO 27017 Controls",
        "Industry and Regulatory Standards/ISO 27018 Controls",
        "Industry and Regulatory Standards/SOC 1",
        "Industry and Regulatory Standards/SOC 2",
        "Industry and Regulatory Standards/HIPAA Controls (USA)",
        "Industry and Regulatory Standards/NIST 800-53 Controls (USA)",
        "Industry and Regulatory Standards/NIST CSF Controls (USA)",
        "Industry and Regulatory Standards/IRAP Controls (Australia)",
        "Industry and Regulatory Standards/K-ISMS Controls (Korea)",
        "Industry and Regulatory Standards/MTCS Controls (Singapore)",
        "Industry and Regulatory Standards/FISC Controls (Japan)",
        "Industry and Regulatory Standards/My Number Act Controls (Japan)",
        "Industry and Regulatory Standards/ENS Controls (Spain)",
        "Industry and Regulatory Standards/Cyber Essentials Plus Controls (UK)",
        "Industry and Regulatory Standards/G-Cloud Controls (UK)",
        "Industry and Regulatory Standards/C5 Controls (Germany)",
        "Industry and Regulatory Standards/IT-Grundschutz Controls (Germany)",
        "Industry and Regulatory Standards/GDPR Controls (Europe)",
        "Industry and Regulatory Standards/TISAX Controls (Europe)",
    ],
    "TTPs": [
        "Initial Access",
        "Execution",
        "Persistence",
        "Privilege Escalation",
        "Defense Evasion",
        "Credential Access",
        "Discovery",
        "Lateral Movement",
        "Collection",
        "Command and Control",
    ],
    "Effects": [
        "Data Exposure",
        "Data Exfiltration",
        "Data Destruction",
        "Denial of Service",
        "Resource Consumption",
    ],
}


def build_vocabulary():
    vocab = []
    for ns, quals in FindingTypes.items():
        for q in quals:
            vocab.append("{}/{}".format(ns, q))
    return vocab


def filter_empty(d):
    for k, v in list(d.items()):
        if not v:
            del d[k]
    return d


class PostFinding(BaseAction):
    """Report a finding to AWS Security Hub.

    Custodian acts as a finding provider, allowing users to craft
    policies that report to the AWS SecurityHub.
    """

    FindingVersion = "2018-10-08"
    ProductName = "default"

    permissions = ('securityhub:BatchImportFindings',)

    schema = type_schema(
        "post-finding",
        required=["types"],
        severity={"type": "number", 'default': 0},
        severity_normalized={"type": "number", "min": 0, "max": 100, 'default': 0},
        confidence={"type": "number", "min": 0, "max": 100},
        criticality={"type": "number", "min": 0, "max": 100},
        recommendation={"type": "string"},
        recommendation_url={"type": "string"},
        fields={"type": "object"},
        types={
            "type": "array",
            "items": {"type": "string", "enum": build_vocabulary()},
        },
        compliance_status={
            "type": "string",
            "enum": ["PASSED", "WARNING", "FAILED", "NOT_AVAILABLE"],
        },
    )

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client("securityhub")
        for resource_set in chunks(resources, 10):
            finding = self.get_finding(resource_set)
            client.batch_import_findings(Findings=[finding])

    def get_finding(self, resources):
        policy = self.manager.ctx.policy
        model = self.manager.resource_type

        now = datetime.utcnow().replace(tzinfo=tzutc()).isoformat()
        finding = {
            "SchemaVersion": self.FindingVersion,
            "ProductArn": "arn:aws:securityhub:{}:{}:product/{}/{}".format(
                self.manager.config.region,
                self.manager.config.account_id,
                self.manager.config.account_id,
                self.ProductName,
            ),
            "AwsAccountId": self.manager.config.account_id,
            "Description": self.data.get(
                "description", policy.data.get("description", "")
            ).strip(),
            "Title": self.data.get("title", policy.name),
            "Id": "{}/{}/{}/{}".format(
                self.manager.config.region,
                self.manager.config.account_id,
                hashlib.md5(json.dumps(policy.data).encode("utf8")).hexdigest(),
                hashlib.md5(
                    json.dumps(list(sorted([r[model.id] for r in resources]))).encode(
                        "utf8"
                    )
                ).hexdigest(),
            ),
            "GeneratorId": policy.name,
            "CreatedAt": now,
            "UpdatedAt": now,
            "RecordState": "ACTIVE",
        }

        severity = {'Product': 0, 'Normalized': 0}
        if self.data.get("severity") is not None:
            severity["Product"] = self.data["severity"]
        if self.data.get("severity_normalized") is not None:
            severity["Normalized"] = self.data["severity_normalized"]
        if severity:
            finding["Severity"] = severity

        recommendation = {}
        if self.data.get("recommendation"):
            recommendation["Text"] = self.data["recommendation"]
        if self.data.get("recommendation_url"):
            recommendation["Url"] = self.data["recommendation_url"]
        if recommendation:
            finding["Remediation"] = {"Recommendation": recommendation}

        if "confidence" in self.data:
            finding["Confidence"] = self.data["confidence"]
        if "criticality" in self.data:
            finding["Criticality"] = self.data["criticality"]
        if "compliance_status" in self.data:
            finding["Compliance"] = {"Status": self.data["compliance_status"]}

        fields = {}
        if "fields" in self.data:
            fields.update(self.data["fields"])
        if not fields:
            tags = {}
            for t in policy.tags:
                if ":" in t:
                    k, v = t.split(":", 1)
                else:
                    k, v = t, ""
                tags[k] = v
            fields = tags
            fields["resource"] = policy.resource_type
            fields["ProviderName"] = "CloudCustodian"
            fields["ProviderVersion"] = version
        if fields:
            finding["ProductFields"] = fields

        finding_resources = []
        for r in resources:
            finding_resources.append(self.format_resource(r))
        finding["Resources"] = finding_resources
        finding["Types"] = list(self.data["types"])
        return filter_empty(finding)

    def format_resource(self, r):
        raise NotImplementedError("subclass responsibility")


@S3.action_registry.register("post-finding")
class BucketFinding(PostFinding):
    def format_resource(self, r):
        owner = r.get("Acl", {}).get("Owner", {})
        resource = {
            "Type": "AwsS3Bucket",
            "Id": "arn:aws:::{}".format(r["Name"]),
            "Region": get_region(r),
            "Tags": {t["Key"]: t["Value"] for t in r.get("Tags", [])},
            "Details": {"AwsS3Bucket": {"OwnerId": owner.get('ID', 'Unknown')}}
        }

        if "DisplayName" in owner:
            resource["Details"]["AwsS3Bucket"]["OwnerName"] = owner['DisplayName']

        return filter_empty(resource)


@EC2.action_registry.register("post-finding")
class InstanceFinding(PostFinding):
    def format_resource(self, r):
        details = {
            "Type": r["InstanceType"],
            "ImageId": r["ImageId"],
            "IpV4Addresses": jmespath.search(
                "NetworkInterfaces[].PrivateIpAddresses[].PrivateIpAddress", r
            ),
            "KeyName": r.get("KeyName"),
            "VpcId": r["VpcId"],
            "SubnetId": r["SubnetId"],
            "LaunchedAt": r["LaunchTime"].isoformat(),
        }

        if "IamInstanceProfile" in r:
            details["IamInstanceProfileArn"] = r["IamInstanceProfile"]["Arn"]

        details = filter_empty(details)

        instance = {
            "Type": "AwsEc2Instance",
            "Id": "arn:aws:{}:{}:instance/{}".format(
                self.manager.config.region,
                self.manager.config.account_id,
                r["InstanceId"]),
            "Region": self.manager.config.region,
            "Tags": {t["Key"]: t["Value"] for t in r.get("Tags", [])},
            "Details": {"AwsEc2Instance": details},
        }

        instance = filter_empty(instance)
        return instance
