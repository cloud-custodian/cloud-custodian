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
from collections import Counter
from datetime import datetime
from dateutil.tz import tzutc

import hashlib
import jmespath
import json

from .core import BaseAction
from c7n.utils import type_schema, local_session, chunks, dumps, filter_empty
from c7n.exceptions import PolicyValidationError

from c7n.manager import resources as aws_resources
from c7n.version import version


FindingTypes = {
    "Software and Configuration Checks",
    "TTPs",
    "Effects",
    "Unusual Behaviors",
    "Sensitive Data Identifications"
}

# Mostly undocumented value size limit
SECHUB_VALUE_SIZE_LIMIT = 1024


class PostFinding(BaseAction):
    """Report a finding to AWS Security Hub.

    Custodian acts as a finding provider, allowing users to craft
    policies that report to the AWS SecurityHub.

    For resources that are taggable, we will tag the resource with an identifier
    such that further findings generate updates.

    Example generate a finding for accounts that don't have shield enabled.

    :example:

    .. code-block:: yaml

      policies:

       - name: account-shield-enabled
         resource: account
         filters:
           - shield-enabled
         actions:
           - type: post-finding
             severity_normalized: 6
             types:
               - "Software and Configuration Checks/Industry and Regulatory Standards/NIST CSF Controls (USA)"
             recommendation: "Enable shield"
             recommendation_url: "https://www.example.com/policies/AntiDDoS.html"
             confidence: 100
             compliance_status: FAILED

    """ # NOQA

    FindingVersion = "2018-10-08"
    ProductName = "default"

    permissions = ('securityhub:BatchImportFindings',)

    schema_alias = True
    schema = type_schema(
        "post-finding",
        required=["types"],
        title={"type": "string"},
        severity={"type": "number", 'default': 0},
        severity_normalized={"type": "number", "min": 0, "max": 100, 'default': 0},
        confidence={"type": "number", "min": 0, "max": 100},
        criticality={"type": "number", "min": 0, "max": 100},
        # Cross region aggregation
        region={'type': 'string', 'description': 'cross-region aggregation target'},
        recommendation={"type": "string"},
        recommendation_url={"type": "string"},
        fields={"type": "object"},
        batch_size={'type': 'integer', 'minimum': 1, 'maximum': 10},
        types={
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
        compliance_status={
            "type": "string",
            "enum": ["PASSED", "WARNING", "FAILED", "NOT_AVAILABLE"],
        },
    )

    NEW_FINDING = 'New'

    def validate(self):
        for finding_type in self.data["types"]:
            if finding_type.count('/') > 2 or finding_type.split('/')[0] not in FindingTypes:
                raise PolicyValidationError(
                    "Finding types must be in the format 'namespace/category/classifier'."
                    " Found {}. Valid namespace values are: {}.".format(
                        finding_type, " | ".join([ns for ns in FindingTypes])))

    def get_finding_tag(self, resource):
        finding_tag = None
        tags = resource.get('Tags', [])

        finding_key = '{}:{}'.format('c7n:FindingId',
            self.data.get('title', self.manager.ctx.policy.name))

        # Support Tags as dictionary
        if isinstance(tags, dict):
            return tags.get(finding_key)

        # Support Tags as list of {'Key': 'Value'}
        for t in tags:
            key = t['Key']
            value = t['Value']
            if key == finding_key:
                finding_tag = value
        return finding_tag

    def group_resources(self, resources):
        grouped_resources = {}
        for r in resources:
            finding_tag = self.get_finding_tag(r) or self.NEW_FINDING
            grouped_resources.setdefault(finding_tag, []).append(r)
        return grouped_resources

    def process(self, resources, event=None):
        region_name = self.data.get('region', self.manager.config.region)
        client = local_session(
            self.manager.session_factory).client(
                "securityhub", region_name=region_name)

        now = datetime.utcnow().replace(tzinfo=tzutc()).isoformat()
        # default batch size to one to work around security hub console issue
        # which only shows a single resource in a finding.
        batch_size = self.data.get('batch_size', 1)
        stats = Counter()
        for key, grouped_resources in self.group_resources(resources).items():
            for resource_set in chunks(grouped_resources, batch_size):
                stats['Finding'] += 1
                if key == self.NEW_FINDING:
                    finding_id = None
                    created_at = now
                    updated_at = now
                else:
                    finding_id, created_at = self.get_finding_tag(
                        resource_set[0]).split(':', 1)
                    updated_at = now

                finding = self.get_finding(
                    resource_set, finding_id, created_at, updated_at)
                import_response = client.batch_import_findings(
                    Findings=[finding])
                if import_response['FailedCount'] > 0:
                    stats['Failed'] += import_response['FailedCount']
                    self.log.error(
                        "import_response=%s" % (import_response))
                if key == self.NEW_FINDING:
                    stats['New'] += len(resource_set)
                    # Tag resources with new finding ids
                    tag_action = self.manager.action_registry.get('tag')
                    if tag_action is None:
                        continue
                    tag_action({
                        'key': '{}:{}'.format(
                            'c7n:FindingId',
                            self.data.get(
                                'title', self.manager.ctx.policy.name)),
                        'value': '{}:{}'.format(
                            finding['Id'], created_at)},
                        self.manager).process(resource_set)
                else:
                    stats['Update'] += len(resource_set)

        self.log.debug(
            "policy:%s securityhub %d findings resources %d new %d updated %d failed",
            self.manager.ctx.policy.name,
            stats['Finding'],
            stats['New'],
            stats['Update'],
            stats['Failed'])

    def get_finding(self, resources, existing_finding_id, created_at, updated_at):
        policy = self.manager.ctx.policy
        model = self.manager.resource_type
        region = self.data.get('region', self.manager.config.region)

        if existing_finding_id:
            finding_id = existing_finding_id
        else:
            finding_id = '{}/{}/{}/{}'.format(
                self.manager.config.region,
                self.manager.config.account_id,
                hashlib.md5(json.dumps(
                    policy.data).encode('utf8')).hexdigest(),
                hashlib.md5(json.dumps(list(sorted(
                    [r[model.id] for r in resources]))).encode(
                        'utf8')).hexdigest())
        finding = {
            "SchemaVersion": self.FindingVersion,
            "ProductArn": "arn:aws:securityhub:{}:{}:product/{}/{}".format(
                region,
                self.manager.config.account_id,
                self.manager.config.account_id,
                self.ProductName,
            ),
            "AwsAccountId": self.manager.config.account_id,
            "Description": self.data.get(
                "description", policy.data.get("description", "")
            ).strip(),
            "Title": self.data.get("title", policy.name),
            'Id': finding_id,
            "GeneratorId": policy.name,
            'CreatedAt': created_at,
            'UpdatedAt': updated_at,
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

        fields = {
            'resource': policy.resource_type,
            'ProviderName': 'CloudCustodian',
            'ProviderVersion': version
        }

        if "fields" in self.data:
            fields.update(self.data["fields"])
        else:
            tags = {}
            for t in policy.tags:
                if ":" in t:
                    k, v = t.split(":", 1)
                else:
                    k, v = t, ""
                tags[k] = v
            fields.update(tags)
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


class OtherResourcePostFinding(PostFinding):

    fields = ()

    def format_resource(self, r):
        details = {}
        for k in r:
            if isinstance(k, (list, dict)):
                continue
            details[k] = r[k]

        for f in self.fields:
            value = jmespath.search(f['expr'], r)
            if not value:
                continue
            details[f['key']] = value

        for k, v in details.items():
            if isinstance(v, datetime):
                v = v.isoformat()
            elif isinstance(v, (list, dict)):
                v = dumps(v)
            elif isinstance(v, (int, float, bool)):
                v = str(v)
            else:
                continue
            details[k] = v[:SECHUB_VALUE_SIZE_LIMIT]

        details['c7n:resource-type'] = self.manager.type
        other = {
            'Type': 'Other',
            'Id': self.manager.get_arns([r])[0],
            'Region': self.manager.config.region,
            'Details': {'Other': filter_empty(details)}
        }
        tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
        if tags:
            other['Tags'] = tags
        return other

    @classmethod
    def register_resource(klass, registry, event):
        for rtype, resource_manager in registry.items():
            if not resource_manager.has_arn():
                continue
            if 'post-finding' in resource_manager.action_registry:
                continue
            resource_manager.action_registry.register('post-finding', klass)


aws_resources.subscribe(
    aws_resources.EVENT_FINAL, OtherResourcePostFinding.register_resource)
