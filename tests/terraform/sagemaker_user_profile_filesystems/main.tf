provider "aws" {}

resource "random_pet" "profile" {
  length = 2
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "filesystems" {
  name_prefix = "c7n-profile-fs-"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    protocol  = "tcp"
    from_port = 2049
    to_port   = 2049
    self      = true
  }
  ingress {
    protocol  = "tcp"
    from_port = 988
    to_port   = 988
    self      = true
  }
  ingress {
    protocol  = "tcp"
    from_port = 1018
    to_port   = 1023
    self      = true
  }
  egress {
    protocol  = "-1"
    from_port = 0
    to_port   = 0
    self      = true
  }
}

resource "aws_efs_file_system" "custom" {
  encrypted = true
  tags      = { Name = "c7n-profile-${random_pet.profile.id}" }
}

resource "aws_efs_mount_target" "custom" {
  file_system_id  = aws_efs_file_system.custom.id
  subnet_id       = data.aws_subnets.default.ids[0]
  security_groups = [aws_security_group.filesystems.id]
}

resource "aws_fsx_lustre_file_system" "custom" {
  storage_capacity   = 1200
  deployment_type    = "SCRATCH_2"
  subnet_ids         = [data.aws_subnets.default.ids[0]]
  security_group_ids = [aws_security_group.filesystems.id]
  tags               = { Name = "c7n-profile-${random_pet.profile.id}" }
}

resource "aws_iam_role" "execution" {
  name = "c7n-profile-fs-${random_pet.profile.id}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "sagemaker.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "filesystems" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "elasticfilesystem:DescribeFileSystems",
          "elasticfilesystem:DescribeMountTargets",
          "fsx:DescribeFileSystems",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_sagemaker_domain" "main" {
  domain_name = "c7n-profile-fs-${random_pet.profile.id}"
  auth_mode   = "IAM"
  vpc_id      = data.aws_vpc.default.id
  subnet_ids  = [data.aws_subnets.default.ids[0]]

  default_user_settings {
    execution_role  = aws_iam_role.execution.arn
    security_groups = [aws_security_group.filesystems.id]
  }
  retention_policy {
    home_efs_file_system = "Delete"
  }
}

resource "aws_sagemaker_user_profile" "main" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-filesystems-${random_pet.profile.id}"
  user_settings {
    execution_role = aws_iam_role.execution.arn
  }
  depends_on = [
    aws_fsx_lustre_file_system.custom,
    aws_efs_mount_target.custom,
    aws_iam_role_policy.filesystems,
  ]
}
