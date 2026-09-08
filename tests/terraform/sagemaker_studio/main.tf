provider "aws" {}

resource "random_pet" "studio" {
  length    = 2
  separator = "-"
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

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "c7n-sagemaker-studio-${random_pet.studio.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_sagemaker_domain" "main" {
  domain_name = "c7n-studio-${random_pet.studio.id}"
  auth_mode   = "IAM"
  vpc_id      = data.aws_vpc.default.id
  subnet_ids  = [data.aws_subnets.default.ids[0]]

  default_user_settings {
    execution_role = aws_iam_role.execution.arn
  }

  default_space_settings {
    execution_role = aws_iam_role.execution.arn
  }

  retention_policy {
    home_efs_file_system = "Delete"
  }
}

resource "aws_sagemaker_user_profile" "main" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-profile-${random_pet.studio.id}"
  tags              = { "favorite-color" = "c7n" }

  user_settings {
    execution_role = aws_iam_role.execution.arn
  }
}

resource "aws_sagemaker_user_profile" "untagged" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-profile-untagged-${random_pet.studio.id}"

  user_settings {
    execution_role = aws_iam_role.execution.arn
  }
}

resource "aws_sagemaker_space" "main" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7nspace${replace(random_pet.studio.id, "-", "")}"
  tags       = { "favorite-color" = "c7n" }
}

resource "aws_sagemaker_space" "untagged" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7nspaceuntagged${replace(random_pet.studio.id, "-", "")}"
}

resource "aws_sagemaker_app" "main" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = aws_sagemaker_user_profile.main.user_profile_name
  app_name          = "c7n-app-${random_pet.studio.id}"
  app_type          = "JupyterServer"
  tags              = { "favorite-color" = "c7n" }
}

resource "aws_sagemaker_app" "untagged" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = aws_sagemaker_user_profile.untagged.user_profile_name
  app_name          = "c7n-app-untagged-${random_pet.studio.id}"
  app_type          = "JupyterServer"
}

output "domain_id" {
  value = aws_sagemaker_domain.main.id
}

output "domain_arn" {
  value = aws_sagemaker_domain.main.arn
}

output "user_profile_name" {
  value = aws_sagemaker_user_profile.main.user_profile_name
}

output "user_profile_arn" {
  value = aws_sagemaker_user_profile.main.arn
}

output "user_profile_untagged_name" {
  value = aws_sagemaker_user_profile.untagged.user_profile_name
}

output "user_profile_untagged_arn" {
  value = aws_sagemaker_user_profile.untagged.arn
}

output "space_name" {
  value = aws_sagemaker_space.main.space_name
}

output "space_arn" {
  value = aws_sagemaker_space.main.arn
}

output "space_untagged_name" {
  value = aws_sagemaker_space.untagged.space_name
}

output "space_untagged_arn" {
  value = aws_sagemaker_space.untagged.arn
}

output "app_name" {
  value = aws_sagemaker_app.main.app_name
}

output "app_arn" {
  value = aws_sagemaker_app.main.arn
}

output "app_untagged_name" {
  value = aws_sagemaker_app.untagged.app_name
}

output "app_untagged_arn" {
  value = aws_sagemaker_app.untagged.arn
}
