# Terraform configuration for EntraID Group testing
# Creates test groups with various configurations for Cloud Custodian policy testing

terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Generate random suffix for unique naming
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Get current client configuration for tenant info
data "azuread_client_config" "current" {}

# Get available domains
data "azuread_domains" "current" {
  only_initial = false
}

# Use the first available domain for user principal names
locals {
  domain_name = data.azuread_domains.current.domains[0].domain_name
}

# Create test users to be members and owners of groups
resource "azuread_user" "test_member1" {
  user_principal_name   = "c7n-test-member1-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Member 1"
  mail_nickname         = "c7n-test-member1-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = true

  lifecycle {
    ignore_changes = [password]
  }
}

resource "azuread_user" "test_member2" {
  user_principal_name   = "c7n-test-member2-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Member 2"
  mail_nickname         = "c7n-test-member2-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = true

  lifecycle {
    ignore_changes = [password]
  }
}

resource "azuread_user" "test_owner" {
  user_principal_name   = "c7n-test-owner-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Owner"
  mail_nickname         = "c7n-test-owner-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = true

  lifecycle {
    ignore_changes = [password]
  }
}

# Test Group 1: Security group with members and owner
resource "azuread_group" "test_security_group" {
  display_name     = "C7N Test Security Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test security group for Cloud Custodian EntraID group testing"
  owners           = [data.azuread_client_config.current.object_id, azuread_user.test_owner.object_id]
}

resource "azuread_group_member" "security_member1" {
  group_object_id  = azuread_group.test_security_group.object_id
  member_object_id = azuread_user.test_member1.object_id
}

resource "azuread_group_member" "security_member2" {
  group_object_id  = azuread_group.test_security_group.object_id
  member_object_id = azuread_user.test_member2.object_id
}

# Test Group 2: Simple second security group (renamed from distribution for clarity)
resource "azuread_group" "test_distribution_group" {
  display_name     = "C7N Test Second Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test second group for Cloud Custodian EntraID group testing"
}

resource "azuread_group_member" "dist_member1" {
  group_object_id  = azuread_group.test_distribution_group.object_id
  member_object_id = azuread_user.test_member1.object_id
}

# Test Group 3: Third security group (dynamic groups require special Azure AD license)
resource "azuread_group" "test_dynamic_group" {
  display_name     = "C7N Test Third Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test third group for Cloud Custodian EntraID group testing"
}

# Test Group 4: Admin group (for admin group detection)
resource "azuread_group" "test_admin_group" {
  display_name     = "C7N Test Admin Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test admin group for Cloud Custodian EntraID group testing"
  owners           = [data.azuread_client_config.current.object_id, azuread_user.test_owner.object_id]
}

resource "azuread_group_member" "admin_member1" {
  group_object_id  = azuread_group.test_admin_group.object_id
  member_object_id = azuread_user.test_member1.object_id
}

# Test Group 5: Empty group (no members, no owner)
resource "azuread_group" "test_empty_group" {
  display_name     = "C7N Test Empty Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test empty group for Cloud Custodian EntraID group testing"
}

# Outputs for pytest-terraform to use
output "test_security_group" {
  value = {
    id               = azuread_group.test_security_group.id
    object_id        = azuread_group.test_security_group.object_id
    display_name     = azuread_group.test_security_group.display_name
    description      = azuread_group.test_security_group.description
    security_enabled = azuread_group.test_security_group.security_enabled
    mail_enabled     = azuread_group.test_security_group.mail_enabled
    group_types      = azuread_group.test_security_group.types
  }
}

output "test_distribution_group" {
  value = {
    id               = azuread_group.test_distribution_group.id
    object_id        = azuread_group.test_distribution_group.object_id
    display_name     = azuread_group.test_distribution_group.display_name
    description      = azuread_group.test_distribution_group.description
    security_enabled = azuread_group.test_distribution_group.security_enabled
    mail_enabled     = azuread_group.test_distribution_group.mail_enabled
    group_types      = azuread_group.test_distribution_group.types
  }
}

output "test_dynamic_group" {
  value = {
    id               = azuread_group.test_dynamic_group.id
    object_id        = azuread_group.test_dynamic_group.object_id
    display_name     = azuread_group.test_dynamic_group.display_name
    description      = azuread_group.test_dynamic_group.description
    security_enabled = azuread_group.test_dynamic_group.security_enabled
    mail_enabled     = azuread_group.test_dynamic_group.mail_enabled
    group_types      = azuread_group.test_dynamic_group.types
  }
}

output "test_admin_group" {
  value = {
    id               = azuread_group.test_admin_group.id
    object_id        = azuread_group.test_admin_group.object_id
    display_name     = azuread_group.test_admin_group.display_name
    description      = azuread_group.test_admin_group.description
    security_enabled = azuread_group.test_admin_group.security_enabled
    mail_enabled     = azuread_group.test_admin_group.mail_enabled
    group_types      = azuread_group.test_admin_group.types
  }
}

output "test_empty_group" {
  value = {
    id               = azuread_group.test_empty_group.id
    object_id        = azuread_group.test_empty_group.object_id
    display_name     = azuread_group.test_empty_group.display_name
    description      = azuread_group.test_empty_group.description
    security_enabled = azuread_group.test_empty_group.security_enabled
    mail_enabled     = azuread_group.test_empty_group.mail_enabled
    group_types      = azuread_group.test_empty_group.types
  }
}

output "test_member1" {
  value = {
    id                  = azuread_user.test_member1.id
    object_id           = azuread_user.test_member1.object_id
    user_principal_name = azuread_user.test_member1.user_principal_name
    display_name        = azuread_user.test_member1.display_name
  }
}

output "test_member2" {
  value = {
    id                  = azuread_user.test_member2.id
    object_id           = azuread_user.test_member2.object_id
    user_principal_name = azuread_user.test_member2.user_principal_name
    display_name        = azuread_user.test_member2.display_name
  }
}

output "test_owner" {
  value = {
    id                  = azuread_user.test_owner.id
    object_id           = azuread_user.test_owner.object_id
    user_principal_name = azuread_user.test_owner.user_principal_name
    display_name        = azuread_user.test_owner.display_name
  }
}
