# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""

**Security Notes**
- All resources request ONLY EntraID permissions, not SharePoint/Exchange/Teams data access
- Microsoft 365 groups may reference connected SharePoint/Teams resources but no direct access
- Unknown status (permission errors) causes resources to be skipped to avoid false results
"""

# Import all EntraID resources to ensure they are properly registered
from c7n_azure.resources.entraid_user import EntraIDUser  # noqa: F401
from c7n_azure.resources.entraid_group import EntraIDGroup  # noqa: F401
from c7n_azure.resources.entraid_organization import EntraIDOrganization  # noqa: F401
