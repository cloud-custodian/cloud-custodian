# Terraform configuration for EntraID User testing
# Creates test users with various configurations for Cloud Custodian policy testing

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
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
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

# Test User 1: Enabled user with admin role (for testing high-privilege detection)
resource "azuread_user" "test_admin_user" {
  user_principal_name   = "c7n-test-admin-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Admin User"
  mail_nickname         = "c7n-test-admin-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = true
  job_title             = "Administrator"
  department            = "IT"

  lifecycle {
    ignore_changes = [password]
  }
}

# Test User 2: Disabled user (for testing disabled account cleanup)
resource "azuread_user" "test_disabled_user" {
  user_principal_name   = "c7n-test-disabled-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Disabled User"
  mail_nickname         = "c7n-test-disabled-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = false
  job_title             = "User"
  department            = "HR"

  lifecycle {
    ignore_changes = [password]
  }
}

# Test User 3: Regular enabled user (for baseline testing)
resource "azuread_user" "test_regular_user" {
  user_principal_name   = "c7n-test-regular-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Regular User"
  mail_nickname         = "c7n-test-regular-${random_string.suffix.result}"
  password              = "P@ssw0rd123!"
  force_password_change = false
  account_enabled       = true
  job_title             = "Developer"
  department            = "Engineering"

  lifecycle {
    ignore_changes = [password]
  }
}

# Test User 4: User with old password (simulate password age testing)
resource "azuread_user" "test_old_password_user" {
  user_principal_name   = "c7n-test-oldpwd-${random_string.suffix.result}@${local.domain_name}"
  display_name          = "C7N Test Old Password User"
  mail_nickname         = "c7n-test-oldpwd-${random_string.suffix.result}"
  password              = "OldP@ssw0rd123!"
  force_password_change = false
  account_enabled       = true
  job_title             = "Analyst"
  department            = "Finance"

  lifecycle {
    ignore_changes = [password]
  }
}

# Create a security group for testing group membership filters
resource "azuread_group" "test_security_group" {
  display_name     = "C7N Test Security Group ${random_string.suffix.result}"
  mail_enabled     = false
  security_enabled = true
  description      = "Test security group for Cloud Custodian EntraID testing"
}

# Add admin user to the security group
resource "azuread_group_member" "admin_member" {
  group_object_id  = azuread_group.test_security_group.object_id
  member_object_id = azuread_user.test_admin_user.object_id
}

# Outputs for pytest-terraform to use
output "test_admin_user" {
  value = {
    id                  = azuread_user.test_admin_user.id
    object_id           = azuread_user.test_admin_user.object_id
    user_principal_name = azuread_user.test_admin_user.user_principal_name
    display_name        = azuread_user.test_admin_user.display_name
    account_enabled     = azuread_user.test_admin_user.account_enabled
    job_title           = azuread_user.test_admin_user.job_title
    department          = azuread_user.test_admin_user.department
  }
}

output "test_disabled_user" {
  value = {
    id                  = azuread_user.test_disabled_user.id
    object_id           = azuread_user.test_disabled_user.object_id
    user_principal_name = azuread_user.test_disabled_user.user_principal_name
    display_name        = azuread_user.test_disabled_user.display_name
    account_enabled     = azuread_user.test_disabled_user.account_enabled
    job_title           = azuread_user.test_disabled_user.job_title
    department          = azuread_user.test_disabled_user.department
  }
}

output "test_regular_user" {
  value = {
    id                  = azuread_user.test_regular_user.id
    object_id           = azuread_user.test_regular_user.object_id
    user_principal_name = azuread_user.test_regular_user.user_principal_name
    display_name        = azuread_user.test_regular_user.display_name
    account_enabled     = azuread_user.test_regular_user.account_enabled
    job_title           = azuread_user.test_regular_user.job_title
    department          = azuread_user.test_regular_user.department
  }
}

output "test_old_password_user" {
  value = {
    id                  = azuread_user.test_old_password_user.id
    object_id           = azuread_user.test_old_password_user.object_id
    user_principal_name = azuread_user.test_old_password_user.user_principal_name
    display_name        = azuread_user.test_old_password_user.display_name
    account_enabled     = azuread_user.test_old_password_user.account_enabled
    job_title           = azuread_user.test_old_password_user.job_title
    department          = azuread_user.test_old_password_user.department
  }
}

output "test_security_group" {
  value = {
    id           = azuread_group.test_security_group.id
    object_id    = azuread_group.test_security_group.object_id
    display_name = azuread_group.test_security_group.display_name
    description  = azuread_group.test_security_group.description
  }
}