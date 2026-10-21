data "aws_region" "current" {}

resource "aws_ecr_repository" "image" {
  name         = "c7n-profile-image-${random_pet.profile.id}"
  force_delete = true
}

resource "terraform_data" "image" {
  input = aws_ecr_repository.image.repository_url

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      IMAGE_URI  = aws_ecr_repository.image.repository_url
      AWS_REGION = data.aws_region.current.region
    }
    command = <<-EOT
      set -euo pipefail
      config=$(mktemp -d)
      trap 'rm -rf "$config"' EXIT
      aws ecr get-login-password --region "$AWS_REGION" | \
        docker --config "$config" login --username AWS --password-stdin \
        "$(echo "$IMAGE_URI" | cut -d/ -f1)"
      for version in initial updated; do
        docker --config "$config" build --platform linux/amd64 \
          --label "c7n.test.version=$version" --tag "$IMAGE_URI:$version" - <<'DOCKERFILE'
      FROM public.ecr.aws/docker/library/python:3.12-slim
      DOCKERFILE
        docker --config "$config" push "$IMAGE_URI:$version"
        docker image rm "$IMAGE_URI:$version"
      done
    EOT
  }
}

resource "aws_iam_role_policy" "image_read" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = aws_ecr_repository.image.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sagemaker:DescribeImage",
          "sagemaker:DescribeImageVersion",
          "sagemaker:DescribeAppImageConfig",
          "sagemaker:DescribeStudioLifecycleConfig",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_sagemaker_image" "app" {
  image_name = "c7n-profile-image-${random_pet.profile.id}"
  role_arn   = aws_iam_role.execution.arn
}

resource "aws_sagemaker_image_version" "initial" {
  image_name = aws_sagemaker_image.app.image_name
  base_image = "${aws_ecr_repository.image.repository_url}:initial"
  aliases    = ["1.0.0"]
  depends_on = [terraform_data.image, aws_iam_role_policy.image_read]
}

resource "aws_sagemaker_image_version" "updated" {
  image_name = aws_sagemaker_image.app.image_name
  base_image = "${aws_ecr_repository.image.repository_url}:updated"
  aliases    = ["2.0.0"]
  depends_on = [aws_sagemaker_image_version.initial]
}

locals {
  app_types = {
    JupyterServerAppSettings = "JupyterServer"
    KernelGatewayAppSettings = "KernelGateway"
    TensorBoardAppSettings   = "TensorBoard"
    RSessionAppSettings      = "RSessionGateway"
    CodeEditorAppSettings    = "CodeEditor"
    JupyterLabAppSettings    = "JupyterLab"
  }
  lifecycle_types = {
    for key, value in local.app_types : key => value
    if contains(["JupyterServer", "KernelGateway", "CodeEditor", "JupyterLab"], value)
  }
  lifecycle_configs = merge([
    for app, app_type in local.lifecycle_types : {
      for kind in ["default", "builtin"] : "${app}-${kind}" => {
        app_type = app_type
        kind     = kind
      }
    }
  ]...)
}

resource "aws_sagemaker_studio_lifecycle_config" "app" {
  for_each = local.lifecycle_configs

  studio_lifecycle_config_name     = "c7n-${lower(each.value.app_type)}-${each.value.kind}-${random_pet.profile.id}"
  studio_lifecycle_config_app_type = each.value.app_type
  studio_lifecycle_config_content  = base64encode("#!/bin/bash\necho c7n-profile-update\n")
}

resource "aws_sagemaker_app_image_config" "app" {
  for_each = toset(["KernelGateway", "JupyterLab", "CodeEditor"])

  app_image_config_name = "c7n-${lower(each.key)}-${random_pet.profile.id}"

  dynamic "kernel_gateway_image_config" {
    for_each = each.key == "KernelGateway" ? [1] : []
    content {
      kernel_spec {
        name         = "python3"
        display_name = "Python 3"
      }
    }
  }

  dynamic "jupyter_lab_image_config" {
    for_each = each.key == "JupyterLab" ? [1] : []
    content {
      file_system_config {
        mount_path  = "/home/sagemaker-user"
        default_uid = 1000
        default_gid = 100
      }
    }
  }

  dynamic "code_editor_app_image_config" {
    for_each = each.key == "CodeEditor" ? [1] : []
    content {
      file_system_config {
        mount_path  = "/home/sagemaker-user"
        default_uid = 1000
        default_gid = 100
      }
    }
  }
}

resource "terraform_data" "rsession_config" {
  input = {
    name   = "c7n-rsession-${random_pet.profile.id}"
    region = data.aws_region.current.region
  }

  # The provider requires a typed config block; RSession uses a name-only config.
  provisioner "local-exec" {
    environment = {
      CONFIG_NAME = self.input.name
      AWS_REGION  = self.input.region
    }
    command = "aws sagemaker create-app-image-config --app-image-config-name \"$CONFIG_NAME\" --region \"$AWS_REGION\""
  }

  provisioner "local-exec" {
    when = destroy
    environment = {
      CONFIG_NAME = self.input.name
      AWS_REGION  = self.input.region
    }
    command = "aws sagemaker delete-app-image-config --app-image-config-name \"$CONFIG_NAME\" --region \"$AWS_REGION\""
  }
}

resource "aws_iam_role" "emr_assumable" {
  name = "c7n-emr-assumable-${random_pet.profile.id}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = aws_iam_role.execution.arn }
    }]
  })
}

resource "aws_sagemaker_user_profile" "app" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-apps-${random_pet.profile.id}"
  user_settings {
    execution_role = aws_iam_role.execution.arn
  }
  depends_on = [
    aws_sagemaker_image_version.updated,
    aws_sagemaker_app_image_config.app,
    terraform_data.rsession_config,
    aws_sagemaker_studio_lifecycle_config.app,
  ]
}

# Managed-image owners are regional, not the account provisioning the profile.
# https://docs.aws.amazon.com/sagemaker/latest/dg/studio-jl.html
locals {
  jupyter_server_image_accounts = {
    "af-south-1"     = "559312083959"
    "ap-east-1"      = "493642496378"
    "ap-northeast-1" = "102112518831"
    "ap-northeast-2" = "806072073708"
    "ap-south-1"     = "394103062818"
    "ap-southeast-1" = "492261229750"
    "ap-southeast-2" = "452832661640"
    "ca-central-1"   = "310906938811"
    "eu-central-1"   = "936697816551"
    "eu-north-1"     = "243637512696"
    "eu-south-1"     = "592751261982"
    "eu-south-2"     = "127363102723"
    "eu-west-1"      = "470317259841"
    "eu-west-2"      = "712779665605"
    "eu-west-3"      = "615547856133"
    "sa-east-1"      = "782484402741"
    "us-east-1"      = "081325390199"
    "us-east-2"      = "429704687514"
    "us-west-1"      = "742091327244"
    "us-west-2"      = "236514542706"
  }
}

output "jupyter_server_image" {
  value = format(
    "arn:aws:sagemaker:%s:%s:image/jupyter-server-3",
    data.aws_region.current.region,
    local.jupyter_server_image_accounts[data.aws_region.current.region],
  )
}

output "lifecycle_configs" {
  value = {
    for key, app_type in local.lifecycle_types : key => {
      default = aws_sagemaker_studio_lifecycle_config.app["${key}-default"].arn
      builtin = aws_sagemaker_studio_lifecycle_config.app["${key}-builtin"].arn
    }
  }
}

output "app_image_configs" {
  value = merge(
    {
      for app_type, config in aws_sagemaker_app_image_config.app :
      app_type => config.app_image_config_name
    },
    { RSessionGateway = terraform_data.rsession_config.output.name },
  )
}
