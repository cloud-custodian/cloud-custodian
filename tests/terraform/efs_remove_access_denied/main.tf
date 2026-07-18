resource "aws_efs_file_system" "example_test" {
  performance_mode = "generalPurpose" # Options: general_purpose, max_io
  encrypted        = true             # Enable encryption at rest

  tags = {
    Name = "example_test"
  }
}

resource "null_resource" "apply_policy_with_bypass" {
  provisioner "local-exec" {
    command = <<EOT
aws efs put-file-system-policy \
  --file-system-id ${aws_efs_file_system.example_test.id} \
  --policy file://efs_policy.json \
  --bypass-policy-lockout-safety-check
EOT
  }
}

# Ensure the policy JSON file exists locally
resource "local_file" "efs_policy_json" {
  filename = "efs_policy.json"
  content = jsonencode({
    Version = "2012-10-17"
    Id      = "DenyAllAccess"
    Statement = [
      {
        Sid       = "DenyAllAccess"
        Effect    = "Deny"
        Principal = { "AWS" : "*" }
        Action    = ["elasticfilesystem:DescribeFileSystemPolicy", "elasticfilesystem:DescribeFileSystems"]
        Resource  = aws_efs_file_system.example_test.arn
      }
    ]
  })
}