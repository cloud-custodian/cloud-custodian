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
  name               = "c7n-profile-update-${random_pet.profile.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_sagemaker_domain" "main" {
  domain_name = "c7n-profile-update-${random_pet.profile.id}"
  auth_mode   = "IAM"
  vpc_id      = data.aws_vpc.default.id
  subnet_ids  = [data.aws_subnets.default.ids[0]]

  default_user_settings {
    execution_role = aws_iam_role.execution.arn
  }

  retention_policy {
    home_efs_file_system = "Delete"
  }
}

resource "aws_sagemaker_user_profile" "main" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-profile-update-${random_pet.profile.id}"

  user_settings {
    execution_role = aws_iam_role.execution.arn

    kernel_gateway_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }

    jupyter_lab_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
      code_repository {
        repository_url = "https://github.com/cloud-custodian/cloud-custodian"
      }
    }

    code_editor_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }
  }
}
