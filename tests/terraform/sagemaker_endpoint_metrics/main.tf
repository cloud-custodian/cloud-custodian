provider "aws" {}

resource "random_pet" "main" {
  length    = 2
  separator = "-"
}

locals {
  name = "c7n-endpoint-metrics-${random_pet.main.id}"
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
  name               = local.name
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

# the bucket name has to contain "sagemaker" for AmazonSageMakerFullAccess to
# grant the execution role access to it
resource "aws_s3_bucket" "model" {
  bucket        = "c7n-sagemaker-endpoint-metrics-${random_pet.main.id}"
  force_destroy = true
}

# see README.md for how model.tar.gz is built
resource "aws_s3_object" "model" {
  bucket = aws_s3_bucket.model.id
  key    = "model.tar.gz"
  source = "${path.module}/model.tar.gz"
  etag   = filemd5("${path.module}/model.tar.gz")
}

data "aws_sagemaker_prebuilt_ecr_image" "xgboost" {
  repository_name = "sagemaker-xgboost"
  image_tag       = "1.7-1"
}

resource "aws_sagemaker_model" "main" {
  name               = local.name
  execution_role_arn = aws_iam_role.execution.arn

  primary_container {
    image          = data.aws_sagemaker_prebuilt_ecr_image.xgboost.registry_path
    model_data_url = "s3://${aws_s3_bucket.model.id}/${aws_s3_object.model.key}"
  }
}

##
## Classic endpoints: the model is attached to each production variant.
##

# Only the second variant is invoked, so an idle-endpoint policy must skip
# this endpoint -- which it can only do by querying every variant.
# A configuration can't be edited, and an endpoint follows its configuration
# by name, so the name has to change for a variant change to reach the
# endpoint -- hence name_prefix, which terraform makes unique. The prefix is
# short because AWS caps it at 37 characters, well under local.name.
resource "aws_sagemaker_endpoint_configuration" "busy" {
  name_prefix = "c7n-em-busy-"

  lifecycle {
    create_before_destroy = true
  }

  production_variants {
    variant_name           = "quiet"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.c5.large"
    initial_variant_weight = 1
  }

  production_variants {
    variant_name           = "busy"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.c5.large"
    initial_variant_weight = 1
  }

  # a gpu variant so the endpoint publishes the GPU metrics; nothing here
  # uses the gpu, but the instance having one is what makes them appear
  production_variants {
    variant_name           = "gpu"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.g4dn.xlarge"
    initial_variant_weight = 1
  }
}

resource "aws_sagemaker_endpoint_configuration" "idle" {
  name_prefix = "c7n-em-idle-"

  lifecycle {
    create_before_destroy = true
  }

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.c5.large"
    initial_variant_weight = 1
  }
}

resource "aws_sagemaker_endpoint" "busy" {
  name                 = "${local.name}-busy"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.busy.name
}

resource "aws_sagemaker_endpoint" "idle" {
  name                 = "${local.name}-idle"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.idle.name
}

##
## Inference-component endpoint: the configuration carries an execution role
## and no variant names a model, so the variant is a compute pool and the
## model arrives as a component placed on it. Such an endpoint reports its
## invocations per component, with no EndpointName dimension at all.
##

resource "aws_sagemaker_endpoint_configuration" "component" {
  name_prefix        = "c7n-em-ic-"
  execution_role_arn = aws_iam_role.execution.arn

  lifecycle {
    create_before_destroy = true
  }

  # an endpoint with inference components can have only one variant, so the
  # pool has a gpu and both components share it -- one reserving the
  # accelerator, one not
  production_variants {
    variant_name           = "AllTraffic"
    instance_type          = "ml.g4dn.xlarge"
    initial_instance_count = 1

    routing_config {
      routing_strategy = "LEAST_OUTSTANDING_REQUESTS"
    }
  }
}

# An endpoint hosting inference components can't be updated to a different
# instance type, so a pool change means replacing the endpoint -- and its
# components with it, hence the stack below follows.
resource "aws_sagemaker_endpoint" "component" {
  name                 = "${local.name}-ic"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.component.name

  lifecycle {
    replace_triggered_by = [aws_sagemaker_endpoint_configuration.component]
  }
}

# Neither the aws provider nor OpenTofu has an inference component resource,
# but cloudformation does, so the stack stands in for one -- destroying the
# stack destroys the component.
resource "aws_cloudformation_stack" "component" {
  name = "${local.name}-ic"

  lifecycle {
    replace_triggered_by = [aws_sagemaker_endpoint.component]
  }

  template_body = jsonencode({
    Resources = {
      Component = {
        Type = "AWS::SageMaker::InferenceComponent"
        Properties = {
          InferenceComponentName = "${local.name}-ic"
          EndpointName           = aws_sagemaker_endpoint.component.name
          VariantName            = "AllTraffic"
          Specification = {
            ModelName = aws_sagemaker_model.main.name
            # every component on a gpu pool has to reserve accelerators,
            # and ml.g4dn.xlarge has one, so the endpoint hosts one component
            ComputeResourceRequirements = {
              MinMemoryRequiredInMb              = 1024
              NumberOfCpuCoresRequired           = 1
              NumberOfAcceleratorDevicesRequired = 1
            }
          }
          RuntimeConfig = { CopyCount = 1 }
        }
      }
    }
  })
}

##
## A component endpoint nothing ever calls. A classic endpoint publishes a
## zero for every interval whether or not it is invoked, but this one
## publishes no invocation data at all, so only a missing-value can decide
## it. Its pool has no gpu, so its component reserves no accelerator.
##

resource "aws_sagemaker_endpoint_configuration" "component_idle" {
  name_prefix        = "c7n-em-ic-idle-"
  execution_role_arn = aws_iam_role.execution.arn

  lifecycle {
    create_before_destroy = true
  }

  production_variants {
    variant_name           = "AllTraffic"
    instance_type          = "ml.c5.large"
    initial_instance_count = 1

    routing_config {
      routing_strategy = "LEAST_OUTSTANDING_REQUESTS"
    }
  }
}

resource "aws_sagemaker_endpoint" "component_idle" {
  name                 = "${local.name}-ic-idle"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.component_idle.name

  lifecycle {
    replace_triggered_by = [aws_sagemaker_endpoint_configuration.component_idle]
  }
}

resource "aws_cloudformation_stack" "component_idle" {
  name = "${local.name}-ic-idle"

  lifecycle {
    replace_triggered_by = [aws_sagemaker_endpoint.component_idle]
  }

  template_body = jsonencode({
    Resources = {
      Component = {
        Type = "AWS::SageMaker::InferenceComponent"
        Properties = {
          InferenceComponentName = "${local.name}-ic-idle"
          EndpointName           = aws_sagemaker_endpoint.component_idle.name
          VariantName            = "AllTraffic"
          Specification = {
            ModelName = aws_sagemaker_model.main.name
            ComputeResourceRequirements = {
              MinMemoryRequiredInMb    = 1024
              NumberOfCpuCoresRequired = 1
            }
          }
          RuntimeConfig = { CopyCount = 1 }
        }
      }
    }
  })
}

output "idle_component_endpoint_name" {
  value = aws_sagemaker_endpoint.component_idle.name
}

# created by the stack, so depend on it rather than on the name alone
output "idle_component_name" {
  value      = "${local.name}-ic-idle"
  depends_on = [aws_cloudformation_stack.component_idle]
}

output "component_endpoint_name" {
  value = aws_sagemaker_endpoint.component.name
}

# created by the stack, so depend on it rather than on the name alone
output "component_name" {
  value      = "${local.name}-ic"
  depends_on = [aws_cloudformation_stack.component]
}
