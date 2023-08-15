resource "aws_elasticsearch_domain" "inbound_connection" {
  domain_name           = "${terraform.workspace}-inbound"
  elasticsearch_version = "7.10"

  cluster_config {
    instance_type = "m4.large.elasticsearch"
  }

  encrypt_at_rest {
    enabled = true
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

resource "aws_elasticsearch_domain" "outbound_connection" {
  domain_name           = "${terraform.workspace}-outbound"
  elasticsearch_version = "7.10"

  cluster_config {
    instance_type = "m4.large.elasticsearch"
  }

  encrypt_at_rest {
    enabled = true
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

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "template_file" "create_connection_output" {
  template = "${path.module}/create_connection_output.json"
}

data "local_file" "create_connection_output" {
  filename = data.template_file.create_connection_output.rendered
  # Comment out depends on after first apply create_connection_output.json when file is created
  depends_on = [null_resource.es_create_outbound_connection]
}

# Create connection command
# Comment this resource out after first apply
resource "null_resource" "es_create_outbound_connection" {
  provisioner "local-exec" {
    command     = "aws es create-outbound-cross-cluster-search-connection --source-domain-info OwnerId='${data.aws_caller_identity.current.account_id}',DomainName='${aws_elasticsearch_domain.outbound_connection.domain_name}',Region='${data.aws_region.current.name}' --destination-domain-info OwnerId='${data.aws_caller_identity.current.account_id}',DomainName='${aws_elasticsearch_domain.inbound_connection.domain_name}',Region='${data.aws_region.current.name}' --connection-alias 'test' >> ${data.template_file.create_connection_output.rendered}"
    interpreter = ["/bin/bash", "-c"]
  }

  depends_on = [
    aws_elasticsearch_domain.inbound_connection,
    aws_elasticsearch_domain.outbound_connection,
    data.aws_caller_identity.current,
    data.aws_region.current
  ]
}

# Accept connection command
# Comment this resource out after first apply
resource "null_resource" "es_accept_connection" {
  provisioner "local-exec" {
    command     = "aws es accept-inbound-cross-cluster-search-connection --cross-cluster-search-connection-id '${jsondecode(data.local_file.create_connection_output.content).CrossClusterSearchConnectionId}'"
    interpreter = ["/bin/bash", "-c"]
  }

  depends_on = [data.local_file.create_connection_output]
}

# Delete Connection comand
# Uncomment this command and run apply before running destroy because connection needs to be deleted before deleting domains
# resource "null_resource" "es_delete_connection"{
#   provisioner "local-exec" {
#     command = "aws es delete-inbound-cross-cluster-search-connection --cross-cluster-search-connection-id '${jsondecode(data.local_file.create_connection_output.content).CrossClusterSearchConnectionId}'"
#     interpreter = ["/bin/bash", "-c"]
#   }

#   depends_on = [data.local_file.create_connection_output]
# }
