# Terraform configuration for EntraID Security Defaults testing
# Configures security defaults policy for Cloud Custodian policy testing

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

# Note: Security defaults cannot be directly managed via Terraform
# as it requires specific permissions and affects the entire tenant.
# Instead, we'll simulate different security defaults configurations
# using data sources and outputs for testing purposes.

# In a real scenario, you would query the actual security defaults policy
# using the Microsoft Graph API or Azure CLI

# Simulate security defaults policy data for testing
locals {
  # Simulate enabled security defaults scenario
  enabled_security_defaults = {
    id                 = "00000000-0000-0000-0000-000000000001"
    display_name       = "Security Defaults"
    description        = "Security defaults provide a set of basic security configurations that help protect your organization"
    is_enabled         = true
    template_id        = "00000000-0000-0000-0000-000000000001"
    created_date_time  = "2021-01-01T00:00:00Z"
    modified_date_time = "2023-01-01T00:00:00Z"
  }

  # Simulate disabled security defaults scenario
  disabled_security_defaults = {
    id                 = "00000000-0000-0000-0000-000000000001"
    display_name       = "Security Defaults"
    description        = "Security defaults provide a set of basic security configurations that help protect your organization"
    is_enabled         = false
    template_id        = "00000000-0000-0000-0000-000000000001"
    created_date_time  = "2021-01-01T00:00:00Z"
    modified_date_time = "2023-01-01T00:00:00Z"
  }
}

# Outputs for pytest-terraform to use
output "security_defaults_enabled" {
  value = local.enabled_security_defaults
}

output "security_defaults_disabled" {
  value = local.disabled_security_defaults
}

# Simulate what security defaults provides when enabled
output "security_defaults_features" {
  value = {
    enabled_features = {
      # MFA enforcement for admins
      require_mfa_for_admins = {
        enabled     = true
        description = "Requires multi-factor authentication for all administrator accounts"
        affected_roles = [
          "Global Administrator",
          "Security Administrator",
          "Conditional Access Administrator",
          "Exchange Administrator",
          "Helpdesk Administrator",
          "Password Administrator",
          "Privileged Authentication Administrator",
          "Privileged Role Administrator",
          "SharePoint Administrator",
          "User Administrator"
        ]
      }

      # MFA enforcement for users when needed
      require_mfa_for_users = {
        enabled     = true
        description = "Requires multi-factor authentication for users when risk is detected"
        trigger_conditions = [
          "Risky sign-in",
          "Unfamiliar location",
          "Anonymous IP address",
          "Malware-linked IP address"
        ]
      }

      # Block legacy authentication
      block_legacy_authentication = {
        enabled     = true
        description = "Blocks legacy authentication protocols that don't support MFA"
        blocked_protocols = [
          "IMAP",
          "MAPI",
          "POP",
          "SMTP",
          "Exchange ActiveSync"
        ]
      }

      # Protect privileged activities
      protect_privileged_activities = {
        enabled     = true
        description = "Requires MFA for privileged activities like accessing Azure portal"
        protected_activities = [
          "Azure portal access",
          "Azure PowerShell",
          "Azure CLI",
          "Microsoft Graph PowerShell"
        ]
      }

      # Enable Microsoft Defender for Identity
      defender_for_identity = {
        enabled     = true
        description = "Enables Microsoft Defender for Identity protection"
        features = [
          "Identity threat detection",
          "Suspicious activity monitoring",
          "Lateral movement detection"
        ]
      }
    }
  }
}

# Simulate security defaults policy compliance status
output "security_defaults_compliance" {
  value = {
    # CIS compliance when security defaults are enabled
    cis_compliant_controls = [
      {
        control                         = "1.1"
        title                           = "Ensure that multi-factor authentication is enabled for all privileged users"
        status                          = "compliant"
        remediated_by_security_defaults = true
      },
      {
        control            = "1.22"
        title              = "Ensure that 'Security defaults' is 'Enabled'"
        status             = "compliant"
        directly_addressed = true
      }
    ]

    # Security improvements provided
    security_improvements = [
      {
        area           = "Authentication"
        improvement    = "MFA enforced for administrators"
        risk_reduction = "High"
      },
      {
        area           = "Legacy Protocols"
        improvement    = "Legacy authentication blocked"
        risk_reduction = "High"
      },
      {
        area           = "Risk Detection"
        improvement    = "User MFA required on risky sign-ins"
        risk_reduction = "Medium"
      },
      {
        area           = "Privileged Access"
        improvement    = "MFA required for Azure management"
        risk_reduction = "High"
      }
    ]

    # Limitations of security defaults
    limitations = [
      "Cannot be customized per user or group",
      "Cannot exclude specific applications",
      "Cannot be combined with conditional access policies",
      "Limited granular control over MFA triggers"
    ]

    # Recommendations for organizations using security defaults
    recommendations = [
      {
        scenario       = "Small organizations (< 50 users)"
        recommendation = "Keep security defaults enabled"
        reason         = "Provides baseline security with minimal configuration"
      },
      {
        scenario       = "Medium organizations (50-300 users)"
        recommendation = "Consider upgrading to conditional access"
        reason         = "More granular control and customization options"
      },
      {
        scenario       = "Large organizations (300+ users)"
        recommendation = "Use conditional access policies"
        reason         = "Full customization and integration with other security tools"
      }
    ]
  }
}

# Test scenarios for different security defaults states
output "test_scenarios" {
  value = {
    # Scenario 1: New tenant with security defaults enabled (recommended)
    new_tenant_secure = {
      security_defaults_enabled   = true
      conditional_access_policies = 0
      mfa_enforced_users          = "administrators_only"
      legacy_auth_blocked         = true
      compliance_score            = 85
      risk_level                  = "low"
    }

    # Scenario 2: Tenant with security defaults disabled and no conditional access (risky)
    disabled_no_ca = {
      security_defaults_enabled   = false
      conditional_access_policies = 0
      mfa_enforced_users          = "none"
      legacy_auth_blocked         = false
      compliance_score            = 25
      risk_level                  = "high"
    }

    # Scenario 3: Tenant with security defaults disabled but conditional access enabled (optimal)
    disabled_with_ca = {
      security_defaults_enabled   = false
      conditional_access_policies = 15
      mfa_enforced_users          = "all_with_exceptions"
      legacy_auth_blocked         = true
      compliance_score            = 95
      risk_level                  = "very_low"
    }
  }
}