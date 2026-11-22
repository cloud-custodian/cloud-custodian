# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""Give the workspace an SSO assignment, for recording only.

See workspace-setup.md, next to this module, for when this runs.
"""

import os
import pathlib
import re
import textwrap

from google.oauth2 import service_account
from googleapiclient import discovery

from c7n_gcp.client import get_workspace_customer, get_workspace_subject

SCOPES = (
    'https://www.googleapis.com/auth/admin.directory.orgunit.readonly',
    'https://www.googleapis.com/auth/cloud-identity.inboundsso',
    )
ORG_UNIT_PATH = '/test-no-enforcement'
IDP_METADATA = pathlib.Path(__file__).parent / 'mock-saml-metadata.xml'


def add_sso_assignment(test) -> None:
    """Federate ORG_UNIT_PATH to mocksaml.com, undone when the test ends.

    An assignment needs a profile, and a profile is rejected as "not
    complete" until it has a credential, so all three are created.
    """
    credentials = service_account.Credentials.from_service_account_file(
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'],
        scopes=list(SCOPES),
        subject=get_workspace_subject(),
        )
    customer = 'customers/%s' % get_workspace_customer()
    identity = discovery.build(
        'cloudidentity', 'v1beta1', credentials=credentials)

    profile = identity.inboundSamlSsoProfiles().create(
        body={
            'customer': customer,
            'displayName': 'c7n test mocksaml',
            'idpConfig': {
                'entityId': _idp_entity_id(),
                'singleSignOnServiceUri': _idp_sign_in_uri(),
                },
            },
        ).execute()['response']['name']
    test.addCleanup(_delete, identity.inboundSamlSsoProfiles(), profile)

    identity.inboundSamlSsoProfiles().idpCredentials().add(
        parent=profile,
        body={'pemData': _idp_certificate()},
        ).execute()

    assignment = identity.inboundSsoAssignments().create(
        body={
            'customer': customer,
            'targetOrgUnit': 'orgUnits/%s' % _org_unit_id(credentials),
            'ssoMode': 'SAML_SSO',
            'samlSsoInfo': {'inboundSamlSsoProfile': profile},
            },
        ).execute()['response']['name']
    # Cleanups run last registered first, so the assignment goes before the
    # profile it refers to.
    test.addCleanup(_delete, identity.inboundSsoAssignments(), assignment)


def _delete(component, name: str) -> None:
    component.delete(name=name).execute()


def _org_unit_id(credentials) -> str:
    """Look the org unit up by path, because only its path is predictable.

    The Directory api prefixes the id with `id:`, which Cloud Identity
    rejects with a 500 rather than a complaint, so drop it.
    """
    directory = discovery.build(
        'admin', 'directory_v1', credentials=credentials)
    units = directory.orgunits().list(
        customerId=get_workspace_customer(), type='all').execute()
    for unit in units['organizationUnits']:
        if unit['orgUnitPath'] == ORG_UNIT_PATH:
            return unit['orgUnitId'].removeprefix('id:')
    raise RuntimeError(
        '%s missing, see the workspace-setup.md next to %s'
        % (ORG_UNIT_PATH, pathlib.Path(__file__).name))


def _idp_metadata() -> str:
    return IDP_METADATA.read_text()


def _idp_entity_id() -> str:
    return re.search(r'entityID="([^"]+)"', _idp_metadata()).group(1)


def _idp_sign_in_uri() -> str:
    """The HTTP-Redirect endpoint, the binding Google assumes."""
    return re.search(
        r'<[^>]*SingleSignOnService[^>]*Binding="[^"]*HTTP-Redirect"'
        r'[^>]*Location="([^"]+)"',
        _idp_metadata()).group(1)


def _idp_certificate() -> str:
    certificate = re.search(
        r'<(?:\w+:)?X509Certificate>\s*([^<]+?)\s*</(?:\w+:)?X509Certificate>',
        _idp_metadata(), re.S).group(1)
    return '-----BEGIN CERTIFICATE-----\n%s\n-----END CERTIFICATE-----\n' % (
        '\n'.join(textwrap.wrap(''.join(certificate.split()), 64)))
