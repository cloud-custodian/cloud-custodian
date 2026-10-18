# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
from datetime import datetime, timedelta, timezone

import requests
from dateutil.parser import parse as parse_date

from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.graph_utils import GraphResourceManager, GraphSource, GraphTypeInfo
from c7n_azure.provider import resources

log = logging.getLogger('custodian.azure.entraid.application')

CREDENTIAL_PROPERTIES = {
    'password': 'passwordCredentials',
    'key': 'keyCredentials',
}


class EntraIDCredentialResource(GraphResourceManager):
    """Shared retrieval for Entra ID objects that carry password and key credentials."""

    collection = None

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        self.source = GraphSource(self)

    def get_graph_resources(self):
        """Get all objects of this collection from Microsoft Graph API."""
        try:
            resources = self.list_graph_collection(f'{self.collection}?$top=999')
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                log.error(
                    f"Insufficient privileges to read {self.collection}. "
                    "Required permission: Application.Read.All"
                )
            raise
        log.debug(f"Retrieved {len(resources)} {self.collection} from Graph API")
        return resources


@resources.register('entraid-application')
class EntraIDApplication(EntraIDCredentialResource):
    """EntraID application registration resource.

    Application registrations hold the client secrets (``passwordCredentials``) and
    certificates (``keyCredentials``) that apps use to authenticate, as shown under
    **Certificates & secrets** in the Azure portal.

    Permissions:
    - Application.Read.All for reading application registrations

    :example:

    Find application registrations with a client secret or certificate that expires
    within the next 30 days or has already expired:

    .. code-block:: yaml

        policies:
          - name: entraid-app-credentials-expiring
            resource: azure.entraid-application
            filters:
              - type: credential-expiration
                days: 30

    :example:

    Find application registrations that still use client secrets:

    .. code-block:: yaml

        policies:
          - name: entraid-app-uses-client-secrets
            resource: azure.entraid-application
            filters:
              - type: value
                key: passwordCredentials
                value: not-null
    """

    collection = 'applications'

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('applications', 'list', None)
        detail_spec = ('applications', 'get', 'id')
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'appId',
            'createdDateTime',
            'signInAudience',
            'id'
        )
        permissions = ('Application.Read.All',)


@resources.register('entraid-service-principal')
class EntraIDServicePrincipal(EntraIDCredentialResource):
    """EntraID service principal (enterprise application) resource.

    Service principals are the tenant-local identities of applications. They can carry
    their own password and key credentials, which are not shown in the Azure portal and
    are typically added through the CLI or API.

    Permissions:
    - Application.Read.All for reading service principals

    :example:

    Find service principals with credentials that expire within the next 14 days,
    ignoring credentials that have already expired:

    .. code-block:: yaml

        policies:
          - name: entraid-sp-credentials-expiring
            resource: azure.entraid-service-principal
            filters:
              - type: credential-expiration
                days: 14
                include-expired: false

    :example:

    Find disabled service principals:

    .. code-block:: yaml

        policies:
          - name: entraid-sp-disabled
            resource: azure.entraid-service-principal
            filters:
              - type: value
                key: accountEnabled
                value: false
    """

    collection = 'servicePrincipals'

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('servicePrincipals', 'list', None)
        detail_spec = ('servicePrincipals', 'get', 'id')
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'appId',
            'servicePrincipalType',
            'accountEnabled',
            'id'
        )
        permissions = ('Application.Read.All',)


@EntraIDApplication.filter_registry.register('credential-expiration')
@EntraIDServicePrincipal.filter_registry.register('credential-expiration')
class CredentialExpirationFilter(Filter):
    """Filter by client secrets and certificates that expire within a number of days.

    A resource matches when at least one of its credentials has an ``endDateTime``
    within ``days`` days from now. Credentials that have already expired match as well
    unless ``include-expired`` is set to ``false``. ``credential-type`` limits the check
    to client secrets (``password``) or certificates (``key``).

    The matching credentials are added to the resource under
    ``c7n:ExpiringCredentials`` with their type, ``keyId``, ``displayName``,
    ``endDateTime`` and ``daysRemaining`` (negative once expired), so notifications
    can say which credential needs rotating.

    :example:

    Find application registrations with a client secret that has already expired:

    .. code-block:: yaml

        policies:
          - name: entraid-app-expired-secrets
            resource: azure.entraid-application
            filters:
              - type: credential-expiration
                days: 0
                credential-type: password
    """

    schema = type_schema(
        'credential-expiration',
        required=['days'],
        days={'type': 'number', 'minimum': 0},
        **{
            'credential-type': {'type': 'string', 'enum': ['all', 'password', 'key']},
            'include-expired': {'type': 'boolean'},
        }
    )

    def validate(self):
        if 'days' not in self.data:
            raise PolicyValidationError(
                f"credential-expiration filter requires 'days' on {self.manager.data}")
        return self

    def process(self, resources, event=None):
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=self.data['days'])
        include_expired = self.data.get('include-expired', True)
        credential_type = self.data.get('credential-type', 'all')
        kinds = (
            list(CREDENTIAL_PROPERTIES) if credential_type == 'all' else [credential_type]
        )

        matched = []
        for resource in resources:
            expiring = []
            for kind in kinds:
                for credential in resource.get(CREDENTIAL_PROPERTIES[kind]) or []:
                    end = self._end_date(credential, resource.get('id'))
                    if end is None or end > threshold:
                        continue
                    if end <= now and not include_expired:
                        continue
                    expiring.append({
                        'type': kind,
                        'keyId': credential.get('keyId'),
                        'displayName': credential.get('displayName'),
                        'endDateTime': credential.get('endDateTime'),
                        'daysRemaining': (end - now).days,
                    })
            if expiring:
                resource['c7n:ExpiringCredentials'] = expiring
                matched.append(resource)
        return matched

    @staticmethod
    def _end_date(credential, resource_id=None):
        """Return the credential's end date as an aware datetime, or None if unusable."""
        value = credential.get('endDateTime')
        if not value:
            return None
        try:
            end = parse_date(value)
        except (TypeError, ValueError, OverflowError):
            log.warning(
                f"Unable to parse credential endDateTime on {resource_id} "
                f"(keyId {credential.get('keyId')}): {value}")
            return None
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return end
