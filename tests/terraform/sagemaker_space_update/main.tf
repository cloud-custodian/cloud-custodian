provider "aws" {}

resource "random_pet" "space" {
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
  name               = "c7n-space-update-${random_pet.space.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_sagemaker_domain" "main" {
  domain_name = "c7n-space-update-${random_pet.space.id}"
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

resource "aws_sagemaker_user_profile" "owner" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-owner-${random_pet.space.id}"
}

# GPU JupyterLab and Code Editor defaults on a private space.
resource "aws_sagemaker_space" "jupyterlab" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7n-jupyterlab-${random_pet.space.id}"

  ownership_settings {
    owner_user_profile_name = aws_sagemaker_user_profile.owner.user_profile_name
  }

  space_sharing_settings {
    sharing_type = "Private"
  }

  space_settings {
    app_type = "JupyterLab"

    jupyter_lab_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }

    code_editor_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }
  }
}

# A Code Editor space with a GPU default.
resource "aws_sagemaker_space" "codeeditor" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7n-codeeditor-${random_pet.space.id}"

  ownership_settings {
    owner_user_profile_name = aws_sagemaker_user_profile.owner.user_profile_name
  }

  space_sharing_settings {
    sharing_type = "Private"
  }

  space_settings {
    app_type = "CodeEditor"

    code_editor_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }
  }
}

# A Studio Classic space: no owner, GPU KernelGateway default. Created last,
# so ListSpaces returns it first.
resource "aws_sagemaker_space" "classic" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7n-classic-${random_pet.space.id}"

  depends_on = [
    aws_sagemaker_space.jupyterlab,
    aws_sagemaker_space.codeeditor,
    aws_sagemaker_space.cpu,
  ]

  space_settings {
    kernel_gateway_app_settings {
      default_resource_spec {
        instance_type = "ml.g4dn.xlarge"
      }
    }
  }
}

# Already on a CPU default.
resource "aws_sagemaker_space" "cpu" {
  domain_id  = aws_sagemaker_domain.main.id
  space_name = "c7n-cpu-${random_pet.space.id}"

  ownership_settings {
    owner_user_profile_name = aws_sagemaker_user_profile.owner.user_profile_name
  }

  space_sharing_settings {
    sharing_type = "Private"
  }

  space_settings {
    app_type = "JupyterLab"

    jupyter_lab_app_settings {
      default_resource_spec {
        instance_type = "ml.t3.large"
      }
    }
  }
}
