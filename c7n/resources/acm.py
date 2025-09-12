# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, ConfigSource, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import type_schema, local_session


class DescribeCertificate(DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super(DescribeCertificate, self).augment(resources))


@resources.register('acm-certificate')
class Certificate(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'acm'
        enum_spec = (
            'list_certificates',
            'CertificateSummaryList',
            {'Includes': {
                'keyTypes': [
                    'RSA_2048', 'RSA_1024', 'RSA_4096',
                    'EC_prime256v1', 'EC_secp384r1',
                    'EC_secp521r1']}})
        id = 'CertificateArn'
        name = 'DomainName'
        date = 'CreatedAt'
        detail_spec = (
            "describe_certificate", "CertificateArn",
            'CertificateArn', 'Certificate')
        cfn_type = "AWS::CertificateManager::Certificate"
        config_type = "AWS::ACM::Certificate"
        arn_type = 'certificate'
        universal_taggable = object()
        permissions_augment = ("acm:ListTagsForCertificate",)

    source_mapping = {
        'describe': DescribeCertificate,
        'config': ConfigSource
    }


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
