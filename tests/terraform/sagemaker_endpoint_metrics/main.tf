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
resource "aws_sagemaker_endpoint_configuration" "busy" {
  name = "${local.name}-busy"

  production_variants {
    variant_name           = "quiet"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
    initial_variant_weight = 1
  }

  production_variants {
    variant_name           = "busy"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
    initial_variant_weight = 1
  }
}

resource "aws_sagemaker_endpoint_configuration" "idle" {
  name = "${local.name}-idle"

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
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
  name               = "${local.name}-ic"
  execution_role_arn = aws_iam_role.execution.arn

  production_variants {
    variant_name           = "AllTraffic"
    instance_type          = "ml.m5.large"
    initial_instance_count = 1

    routing_config {
      routing_strategy = "LEAST_OUTSTANDING_REQUESTS"
    }
  }
}

resource "aws_sagemaker_endpoint" "component" {
  name                 = "${local.name}-ic"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.component.name
}

# Neither the aws provider nor OpenTofu has an inference component resource,
# but cloudformation does, so the stack stands in for one -- destroying the
# stack destroys the component.
resource "aws_cloudformation_stack" "component" {
  name = "${local.name}-ic"

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

output "component_endpoint_name" {
  value = aws_sagemaker_endpoint.component.name
}

# created by the stack, so depend on it rather than on the name alone
output "component_name" {
  value      = "${local.name}-ic"
  depends_on = [aws_cloudformation_stack.component]
}
