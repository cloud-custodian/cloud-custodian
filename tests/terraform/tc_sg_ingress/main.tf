terraform {
  required_providers {
    tencentcloud = {
      source = "tencentcloudstack/tencentcloud"
    }
  }
}

provider "tencentcloud" {}

resource "tencentcloud_security_group" "allow_all_ingress" {
  name        = "sg-allow-all-ingress"
  description = "Allow all ingress"
}

resource "tencentcloud_security_group_rule_set" "ingress_all" {
  security_group_id = tencentcloud_security_group.allow_all_ingress.id

  ingress {
    action      = "ACCEPT"
    cidr_block  = "0.0.0.0/0"
    protocol    = "ALL"
    port        = "ALL"
    description = "Allow all ingress"
  }
}

resource "tencentcloud_security_group" "allow_tcp_ingress" {
  name        = "sg-allow-tcp-ingress"
  description = "Allow TCP ingress"
}

resource "tencentcloud_security_group_rule_set" "ingress_tcp" {
  security_group_id = tencentcloud_security_group.allow_tcp_ingress.id

  ingress {
    action      = "ACCEPT"
    cidr_block  = "0.0.0.0/0"
    protocol    = "TCP"
    port        = "ALL"
    description = "Allow all TCP ingress"
  }
}

resource "tencentcloud_security_group" "deny_all_ingress" {
  name        = "sg-deny-all-ingress"
  description = "Deny all ingress"
}

resource "tencentcloud_security_group_rule_set" "deny_all" {
  security_group_id = tencentcloud_security_group.deny_all_ingress.id

  ingress {
    action      = "DROP"
    cidr_block  = "0.0.0.0/0"
    protocol    = "ALL"
    port        = "ALL"
    description = "Deny all ingress"
  }
}
