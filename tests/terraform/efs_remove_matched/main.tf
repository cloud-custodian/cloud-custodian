resource "aws_efs_file_system" "example" {
  performance_mode = "generalPurpose" # Options: general_purpose, max_io
  encrypted        = true             # Enable encryption at rest

  tags = {
    Name = "example-efs"
  }
}

resource "aws_efs_file_system_policy" "example" {
  file_system_id = aws_efs_file_system.example.id

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "ExampleEFSResourcePolicy"
    Statement = [
      {
        Sid       = "PublicAllowAccess"
        Effect    = "Allow"
        Principal = { "AWS" : "*" }
        Action    = "elasticfilesystem:ClientWrite"
        Resource  = aws_efs_file_system.example.arn
      },
      {
        Sid       = "SpecificAllow"
        Effect    = "Allow"
        Principal = { "AWS" : "arn:aws:iam::185106417252:root" },
        Action    = "elasticfilesystem:ClientWrite"
        Resource  = aws_efs_file_system.example.arn
      },

    ]
  })
}

resource "aws_efs_file_system" "example_client_error" {
  performance_mode = "generalPurpose" # Options: general_purpose, max_io
  encrypted        = true             # Enable encryption at rest

  tags = {
    Name = "example_client_error"
  }
}

resource "aws_efs_file_system_policy" "example_client_error" {
  file_system_id = aws_efs_file_system.example_client_error.id

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "WhatIsIt"
    Statement = [
      {
        Sid       = "WhatIsIt"
        Effect    = "Allow"
        Principal = { "AWS" : "*" }
        Action    = ["elasticfilesystem:DescribeFileSystemPolicy", "elasticfilesystem:DescribeFileSystems"]
        Resource  = aws_efs_file_system.example_client_error.arn
      }
    ]
  })
}

resource "aws_efs_file_system" "example_remove_named" {
  performance_mode = "generalPurpose" # Options: general_purpose, max_io
  encrypted        = true             # Enable encryption at rest
  tags = {
    Name = "example_remove_named"
  }
}

resource "aws_efs_file_system_policy" "example_remove_named" {
  file_system_id = aws_efs_file_system.example_remove_named.id

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "ExampleEFSResourcePolicy"
    Statement = [
      {
        Sid       = "SpecificAllow"
        Effect    = "Allow"
        Principal = { "AWS" : "*" }
        Action    = "elasticfilesystem:ClientWrite"
        Resource  = aws_efs_file_system.example_remove_named.arn
      },
      {
        Sid       = "RemoveMe"
        Effect    = "Allow"
        Principal = { "AWS" : "*" },
        Action    = "elasticfilesystem:ClientWrite"
        Resource  = aws_efs_file_system.example_remove_named.arn
      }
    ]
  })
}
