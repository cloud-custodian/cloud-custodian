resource "random_id" "id" {
  byte_length = 4
}

# MSK Cluster - using smallest instance type for cost efficiency
resource "aws_msk_cluster" "test" {
  cluster_name           = "c7n-test-${random_id.id.hex}"
  kafka_version          = "3.5.1"
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets  = aws_subnet.msk[*].id
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 10
      }
    }
  }

  # Enable enhanced monitoring for metrics testing
  enhanced_monitoring = "PER_BROKER"

  tags = {
    Name        = "c7n-test-msk-${random_id.id.hex}"
    Environment = "test"
  }
}

output "cluster_arn" {
  value = aws_msk_cluster.test.arn
}

output "cluster_name" {
  value = aws_msk_cluster.test.cluster_name
}

output "bootstrap_brokers" {
  value = aws_msk_cluster.test.bootstrap_brokers
}

