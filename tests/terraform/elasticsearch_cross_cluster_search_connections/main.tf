resource "aws_elasticsearch_domain" "inbound-connection" {
  domain_name           = "${terraform.workspace}-inbound"
  elasticsearch_version = "7.10"

  cluster_config {
    instance_type = "m4.large.elasticsearch"
  }

  encrypt_at_rest {
    enabled    = true
  }

  node_to_node_encryption {
    enabled = true
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true
    master_user_options {
      master_user_name     = "test"
      master_user_password = "Test!1234"
    }
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
}

resource "aws_elasticsearch_domain" "outbound-connection" {
  domain_name           = "${terraform.workspace}-outbound"
  elasticsearch_version = "7.10"

  cluster_config {
    instance_type = "m4.large.elasticsearch"
  }

  encrypt_at_rest {
    enabled    = true
  }

  node_to_node_encryption {
    enabled = true
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true
    master_user_options {
      master_user_name     = "test"
      master_user_password = "Test!1234"
    }
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
}

# and then run these command from CLI to create cross cluster connection
# aws es create-outbound-cross-cluster-search-connection --source-domain-info OwnerId="[AccountID]",DomainName="default-outbound",Region="us-east-1" --destination-domain-info OwnerId="[AccountID]",DomainName="default-inbound",Region="us-east-1" --connection-alias "test2"
# aws es accept-inbound-cross-cluster-search-connection --cross-cluster-search-connection-id "[CrossClusterSearchConnectionId]"