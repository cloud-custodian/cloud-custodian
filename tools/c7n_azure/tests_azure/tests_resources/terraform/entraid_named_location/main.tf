# Terraform configuration for EntraID Named Location testing
# Creates test named locations for Cloud Custodian policy testing

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

# Get current client configuration
data "azuread_client_config" "current" {}

# Test IP Named Location 1: Corporate IP ranges (changed to untrusted to avoid deletion issues)
resource "azuread_named_location" "test_corporate_ips" {
  display_name = "C7N Test - Corporate IP Ranges ${random_string.suffix.result}"

  ip {
    ip_ranges = [
      "192.168.1.0/24",
      "10.0.0.0/16",
      "172.16.0.0/12"
    ]
    trusted = false # Changed to false to avoid Azure AD deletion restrictions
  }
}

# Test IP Named Location 2: Untrusted external IP ranges
resource "azuread_named_location" "test_external_ips" {
  display_name = "C7N Test - External IP Ranges ${random_string.suffix.result}"

  ip {
    ip_ranges = [
      "203.0.113.0/24",
      "198.51.100.0/24"
    ]
    trusted = false
  }
}

# Test IP Named Location 3: Single IP address (changed to untrusted to avoid deletion issues)
resource "azuread_named_location" "test_single_ip" {
  display_name = "C7N Test - Single IP ${random_string.suffix.result}"

  ip {
    ip_ranges = [
      "192.168.1.100/32"
    ]
    trusted = false # Changed to false to avoid Azure AD deletion restrictions
  }
}

# Test Country Named Location 1: Multiple trusted countries
resource "azuread_named_location" "test_trusted_countries" {
  display_name = "C7N Test - Trusted Countries ${random_string.suffix.result}"

  country {
    countries_and_regions = [
      "US",
      "CA",
      "GB",
      "AU"
    ]
    include_unknown_countries_and_regions = false
  }
}

# Test Country Named Location 2: Single country with unknown regions included
resource "azuread_named_location" "test_country_with_unknown" {
  display_name = "C7N Test - Country with Unknown Regions ${random_string.suffix.result}"

  country {
    countries_and_regions = [
      "US"
    ]
    include_unknown_countries_and_regions = true
  }
}

# Test Country Named Location 3: High-risk countries (blocked regions)
resource "azuread_named_location" "test_blocked_countries" {
  display_name = "C7N Test - Blocked Countries ${random_string.suffix.result}"

  country {
    countries_and_regions = [
      "CN",
      "RU",
      "KP"
    ]
    include_unknown_countries_and_regions = false
  }
}

# Test IP Named Location 4: Multiple valid IP ranges (changed to untrusted to avoid deletion issues)
resource "azuread_named_location" "test_mixed_ranges" {
  display_name = "C7N Test - Multiple IP Ranges ${random_string.suffix.result}"

  ip {
    ip_ranges = [
      "192.168.10.0/24",
      "172.20.0.0/16",
      "203.0.114.0/24"
    ]
    trusted = false # Changed to false to avoid Azure AD deletion restrictions
  }
}

# Outputs for pytest-terraform to use
output "test_corporate_ips" {
  value = {
    id           = azuread_named_location.test_corporate_ips.id
    object_id    = azuread_named_location.test_corporate_ips.id
    display_name = azuread_named_location.test_corporate_ips.display_name
    ip = {
      ip_ranges_or_fqdns = azuread_named_location.test_corporate_ips.ip[0].ip_ranges
      trusted            = azuread_named_location.test_corporate_ips.ip[0].trusted
    }
  }
}

output "test_external_ips" {
  value = {
    id           = azuread_named_location.test_external_ips.id
    object_id    = azuread_named_location.test_external_ips.id
    display_name = azuread_named_location.test_external_ips.display_name
    ip = {
      ip_ranges_or_fqdns = azuread_named_location.test_external_ips.ip[0].ip_ranges
      trusted            = azuread_named_location.test_external_ips.ip[0].trusted
    }
  }
}

output "test_single_ip" {
  value = {
    id           = azuread_named_location.test_single_ip.id
    object_id    = azuread_named_location.test_single_ip.id
    display_name = azuread_named_location.test_single_ip.display_name
    ip = {
      ip_ranges_or_fqdns = azuread_named_location.test_single_ip.ip[0].ip_ranges
      trusted            = azuread_named_location.test_single_ip.ip[0].trusted
    }
  }
}

output "test_trusted_countries" {
  value = {
    id           = azuread_named_location.test_trusted_countries.id
    object_id    = azuread_named_location.test_trusted_countries.id
    display_name = azuread_named_location.test_trusted_countries.display_name
    country = {
      countries_and_regions                 = azuread_named_location.test_trusted_countries.country[0].countries_and_regions
      include_unknown_countries_and_regions = azuread_named_location.test_trusted_countries.country[0].include_unknown_countries_and_regions
    }
  }
}

output "test_country_with_unknown" {
  value = {
    id           = azuread_named_location.test_country_with_unknown.id
    object_id    = azuread_named_location.test_country_with_unknown.id
    display_name = azuread_named_location.test_country_with_unknown.display_name
    country = {
      countries_and_regions                 = azuread_named_location.test_country_with_unknown.country[0].countries_and_regions
      include_unknown_countries_and_regions = azuread_named_location.test_country_with_unknown.country[0].include_unknown_countries_and_regions
    }
  }
}

output "test_blocked_countries" {
  value = {
    id           = azuread_named_location.test_blocked_countries.id
    object_id    = azuread_named_location.test_blocked_countries.id
    display_name = azuread_named_location.test_blocked_countries.display_name
    country = {
      countries_and_regions                 = azuread_named_location.test_blocked_countries.country[0].countries_and_regions
      include_unknown_countries_and_regions = azuread_named_location.test_blocked_countries.country[0].include_unknown_countries_and_regions
    }
  }
}

output "test_mixed_ranges" {
  value = {
    id           = azuread_named_location.test_mixed_ranges.id
    object_id    = azuread_named_location.test_mixed_ranges.id
    display_name = azuread_named_location.test_mixed_ranges.display_name
    ip = {
      ip_ranges_or_fqdns = azuread_named_location.test_mixed_ranges.ip[0].ip_ranges
      trusted            = azuread_named_location.test_mixed_ranges.ip[0].trusted
    }
  }
}

# Summary output with all named location IDs for easier access
output "all_named_locations" {
  value = {
    corporate_ips        = azuread_named_location.test_corporate_ips.id
    external_ips         = azuread_named_location.test_external_ips.id
    single_ip            = azuread_named_location.test_single_ip.id
    trusted_countries    = azuread_named_location.test_trusted_countries.id
    country_with_unknown = azuread_named_location.test_country_with_unknown.id
    blocked_countries    = azuread_named_location.test_blocked_countries.id
    mixed_ranges         = azuread_named_location.test_mixed_ranges.id
  }
}
