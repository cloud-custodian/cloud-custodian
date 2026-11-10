.. _gcp_workspace_users:

Workspace Users - find users without MFA
========================================

Google Workspace (Cloud Identity) users are not GCP resources. They
are read through the Admin SDK Directory API, which differs from the
rest of the GCP provider in two ways: it is scoped to a Workspace
account, called a "customer", rather than a project, and it is
authorized by domain wide delegation rather than by GCP IAM::

  +-----------------------------------------------------------------------+
  |  GOOGLE WORKSPACE                                                     |
  |                                                                       |
  |   +---------------------------------------------------------------+   |
  |   |  Workspace user account that can list user meta data          |   |
  |   +---------------------------------------------------------------+   |
  |                                                       ^               |
  +-------------------------------------------------------|---------------+
                                                          |
                                   2. Impersonates User   |
                                      (OAuth 2.0 Access   |
                                       Token generated)   |
                                                          |
  +-------------------------------------------------------|---------------+
  |  GOOGLE CLOUD PLATFORM (GCP) PROJECT                  |               |
  |                                                       |               |
  |   +---------------------------------------------------+-----------+   |
  |   |  GCP Service Account                                          |   |
  |   |  - Client ID (OAuth 2.0 Identifier)                           |   |
  |   |  - Holds private key credentials                              |   |
  |   |  - Has been configured in the workspace via                   |   |
  |   |    domain-wide-delegation to be able to list user meta data   |   |
  |   |    (admin.directory.user.readonly scope)                      |   |
  |   +---------------------------------------------------------------+   |
  |                               ^                                       |
  |                               | 1. Authenticates & requests token     |
  |                               |                                       |
  |   +---------------------------+---+                                   |
  |   |  C7n policy run               |                                   |
  |   |  - Uses Workspace API Client  |                                   |
  |   +-------------------------------+                                   |
  +-----------------------------------------------------------------------+

The service account lives in a GCP project. The users, and the user whose
``Users > Read`` privilege is borrowed to read them, live in the Workspace.
The GCP service account is connected to the Workspace using
domain-wide-delegation configuration in the Workspace, so the service account
can live in any project. Which user it impersonates is chosen at run time by
``GOOGLE_WORKSPACE_SUBJECT``.

Setup needed to use these resources
-----------------------------------

You need a GCP service account that a Workspace super administrator has
authorized, and a Workspace user for it to impersonate. The impersonated
user needs only the ``Users > Read`` privilege, not super admin.

1. Create a service account, in the GCP console under
   IAM & Admin > Service Accounts. It can live in any project.

2. Give it a key: select the account, then Keys > Add key > Create new key,
   choose JSON, and keep the file it downloads. Delegation signs its own
   JWT, so a key file is needed rather than the ambient credentials the
   rest of the provider can use.

   Two of its fields matter below:

   ``client_id``
     The numeric id, shown in the console as the service account's "Unique
     ID". This is what step 4 asks for.

   ``client_email``
     Identifies the service account, but is *not* what step 4 asks for.

3. Enable the APIs these policies call, in the same project under
   APIs & Services > Library: **Admin SDK API** and **Cloud Identity API**.

4. Authorize the delegation. Sign in to https://admin.google.com as a super
   administrator, go to Security > Access and data control > API controls >
   Manage Domain-Wide Delegation, click "Add new", and enter the service
   account's ``client_id`` with these scopes:

   ``https://www.googleapis.com/auth/admin.directory.user.readonly``
     Listing users.

   ``https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly``
     The SSO check described under `Caveats`_.

   Both are required. Delegation authorizes exactly the scopes requested
   and a broader grant does not imply a narrower one, so omitting either
   fails the run when its token is requested. Changes here can take a few
   minutes to take effect.

Then, when running policies, the following environment variables must be set:

``GOOGLE_APPLICATION_CREDENTIALS``
  Path to the key file downloaded above.

``GOOGLE_WORKSPACE_SUBJECT``
  The Workspace user with the ``Users > Read`` privilege to
  impersonate. Delegation is only attempted when this is set.

In addition, you may need:

``GOOGLE_WORKSPACE_CUSTOMER``
  Optional customer (Workspace account) id. Defaults to
  ``my_customer``, which resolves to the customer (Workspace) the
  impersonated subject belongs to, so the usual single Workspace case
  needs no configuration. Set it when the subject can administer more
  than one customer, or to pin the target explicitly.

A run targets one customer, so scanning several means several runs. Because
the resource is customer scoped rather than project scoped, it should be
excluded from per project sweeps, which would otherwise report the same
users once per project.

Finding users without MFA
-------------------------

The Directory API reports 2 step verification, Google's term for MFA, per
user. Suspended users cannot sign in, so they are excluded to avoid noise.

.. code-block:: yaml

    policies:
      - name: gcp-workspace-users-without-mfa
        description: |
          Workspace users that have not enrolled in 2 step verification.
        resource: gcp.workspace-user
        filters:
          - type: value
            key: isEnrolledIn2Sv
            value: false
          - type: value
            key: suspended
            value: false

Caveats
-------

``isEnrolledIn2Sv`` and ``isEnforcedIn2Sv`` report whether a second factor is
present or required, not which type it is. The Directory user resource does
not expose security key information, so security key enforcement cannot be
audited through this resource.

``isAdmin`` denotes a Workspace *super* administrator. Users holding
a narrower delegated role appear as ``isDelegatedAdmin`` instead, and neither
is the same as a GCP ``roles/resourcemanager.organizationAdmin`` binding.

If your organization authenticates through an external identity provider,
sign in may be handled there rather than by Google, in which case
``isEnrolledIn2Sv`` describes a factor Google may never ask for. Which
provider governs a given user depends on the org unit and group an inbound
SSO assignment targets, and that isn't resolved here yet. Rather than report
two step verification as though it were protection, policies fail when the
Workspace has any inbound SSO assignment.
