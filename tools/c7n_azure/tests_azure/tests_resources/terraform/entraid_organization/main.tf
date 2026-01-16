# Terraform configuration for EntraID Organization testing
# Configures organization-level settings for Cloud Custodian policy testing

terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.0"
    }
  }
}

# Get current client configuration
data "azuread_client_config" "current" {}

# Get current domains
data "azuread_domains" "current" {
  only_initial = false
}

# Note: Most organization settings cannot be modified via Terraform
# as they require global admin privileges and could affect the entire tenant.
# Instead, we'll use data sources to read current organization settings
# and create test outputs that simulate different organization configurations.

# Create outputs for pytest-terraform to use
# These represent typical organization configurations for testing

output "organization_basic_info" {
  value = {
    id                  = data.azuread_client_config.current.tenant_id
    display_name        = "Test Organization" # Static for testing
    tenant_id           = data.azuread_client_config.current.tenant_id
    object_id           = data.azuread_client_config.current.object_id
    client_id           = data.azuread_client_config.current.client_id
    country_letter_code = "US" # Static for testing
    preferred_language  = "en" # Static for testing
    privacy_profile     = []   # Static for testing
    technical_contacts  = []   # Static for testing
    marketing_contacts  = []   # Static for testing
  }
}

output "organization_domains" {
  value = {
    domains = [for domain in data.azuread_domains.current.domains : {
      domain_name         = domain.domain_name
      authentication_type = domain.authentication_type
      is_default          = domain.domain_name == data.azuread_domains.current.domains[0].domain_name
      is_initial          = domain.domain_name == data.azuread_domains.current.domains[0].domain_name
      is_verified         = true
    }]
  }
}

# Simulate organization security settings for testing
# In a real scenario, these would be read from actual organization policies
output "organization_security_settings" {
  value = {
    # Simulated security defaults status
    security_defaults_enabled = true

    # Simulated password policy settings
    password_policy = {
      minimum_length             = 8
      require_lowercase          = true
      require_uppercase          = true
      require_numbers            = true
      require_special_characters = true
      password_history_count     = 24
      max_password_age_days      = 90
      min_password_age_days      = 1
      lockout_threshold          = 5
      lockout_duration_minutes   = 30
    }

    # Simulated conditional access settings
    conditional_access = {
      baseline_policies_enabled   = true
      require_mfa_for_admins      = true
      block_legacy_authentication = true
      require_compliant_devices   = false
    }

    # Simulated guest access settings
    guest_access = {
      guest_users_can_invite   = false
      guests_can_access_groups = true
      restrict_guest_access    = "restrictive"
    }

    # Simulated directory settings
    directory_settings = {
      users_can_register_apps   = false
      users_can_create_groups   = true
      users_can_add_guests      = false
      restrict_directory_access = true
    }
  }
}

# Simulate compliance status for testing
output "organization_compliance" {
  value = {
    # CIS Microsoft Azure Foundations Benchmark compliance status
    cis_compliance = {
      version = "1.5.0"
      controls = {
        "1.1"  = { title = "Ensure that multi-factor authentication is enabled for all privileged users", status = "compliant" }
        "1.2"  = { title = "Ensure that there are no guest users", status = "non_compliant" }
        "1.3"  = { title = "Ensure that there are no users with admin roles", status = "non_compliant" }
        "1.4"  = { title = "Ensure guest users are reviewed on a monthly basis", status = "compliant" }
        "1.5"  = { title = "Ensure that there are no users with permanent roles assigned", status = "compliant" }
        "1.22" = { title = "Ensure that 'Security defaults' is 'Enabled'", status = "compliant" }
      }
    }

    # NIST compliance indicators
    nist_compliance = {
      framework = "NIST 800-53 Rev 5"
      controls = {
        "AC-2" = { title = "Account Management", status = "compliant" }
        "AC-3" = { title = "Access Enforcement", status = "compliant" }
        "AC-6" = { title = "Least Privilege", status = "partially_compliant" }
        "IA-2" = { title = "Identification and Authentication", status = "compliant" }
        "IA-5" = { title = "Authenticator Management", status = "compliant" }
      }
    }
  }
}

# Test organization for different tenant scenarios
output "test_tenant_scenarios" {
  value = {
    # Small organization scenario
    small_org = {
      user_count                  = 50
      admin_count                 = 2
      guest_count                 = 5
      group_count                 = 10
      app_count                   = 15
      conditional_access_policies = 3
      has_premium_licenses        = false
      has_security_defaults       = true
    }

    # Medium organization scenario  
    medium_org = {
      user_count                  = 500
      admin_count                 = 8
      guest_count                 = 25
      group_count                 = 75
      app_count                   = 100
      conditional_access_policies = 12
      has_premium_licenses        = true
      has_security_defaults       = false
    }

    # Large organization scenario
    large_org = {
      user_count                  = 5000
      admin_count                 = 25
      guest_count                 = 100
      group_count                 = 300
      app_count                   = 500
      conditional_access_policies = 50
      has_premium_licenses        = true
      has_security_defaults       = false
    }
  }
}