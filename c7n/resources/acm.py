# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, ConfigSource, TypeInfo
from c7n.tags import universal_augment, register_universal_tags
from c7n.utils import type_schema, local_session


@resources.register('acm-certificate')
class Certificate(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'acm'
        enum_spec = ('list_certificates', 'CertificateSummaryList', None)
        id = 'CertificateArn'
        name = 'DomainName'
        date = 'CreatedAt'
        detail_spec = (
            "describe_certificate", "CertificateArn",
            'CertificateArn', 'Certificate')
        config_type = "AWS::ACM::Certificate"
        arn_type = 'certificate'
        universal_taggable = object()

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeCertificate(self)
        elif source_type == 'config':
            return ConfigSource(self)
        raise ValueError("Unsupported source: %s for %s" % (
            source_type, self.resource_type.config_type))


class DescribeCertificate(DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super(DescribeCertificate, self).augment(resources))


register_universal_tags(Certificate.filter_registry, Certificate.action_registry)


@Certificate.action_registry.register('delete')
class CertificateDeleteAction(BaseAction):
    """Action to delete an ACM Certificate
    To avoid unwanted deletions of certificates, it is recommended to apply a filter
    to the rule
    :example:

    .. code-block:: yaml

        policies:
          - name: acm-certificate-delete-expired
            resource: acm-certificate
            filters:
              - type: value
                key: NotAfter
                value_type: expiration
                op: lt
                value: 0
            actions:
              - delete
    """

    schema = type_schema('delete')
    permissions = (
        "acm:DeleteCertificate",
    )

    def process(self, certificates):
        client = local_session(self.manager.session_factory).client('acm')
        for cert in certificates:
            self.process_cert(client, cert)

    def process_cert(self, client, cert):
        try:
            self.manager.retry(
                client.delete_certificate, CertificateArn=cert['CertificateArn'])
        except client.exceptions.ResourceNotFoundException:
            pass
        except client.exceptions.ResourceInUseException as e:
            self.log.warning(
                "Exception trying to delete Certificate: %s error: %s",
                cert['CertificateArn'], e)
