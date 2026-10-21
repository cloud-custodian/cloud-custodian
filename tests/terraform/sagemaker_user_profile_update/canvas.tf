data "aws_iam_policy_document" "canvas_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type = "Service"
      identifiers = [
        "sagemaker.amazonaws.com",
        "forecast.amazonaws.com",
        "bedrock.amazonaws.com",
        "emr-serverless.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role" "canvas" {
  name               = "c7n-canvas-${random_pet.profile.id}"
  assume_role_policy = data.aws_iam_policy_document.canvas_assume_role.json
}

resource "aws_secretsmanager_secret" "oauth" {
  name_prefix             = "c7n-profile-oauth-"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "oauth" {
  secret_id = aws_secretsmanager_secret.oauth.id
  secret_string = jsonencode({
    client_id     = "c7n-test-client"
    client_secret = "c7n-test-secret"
  })
}

resource "aws_secretsmanager_secret" "oauth_initial" {
  name_prefix             = "c7n-profile-oauth-initial-"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "oauth_initial" {
  secret_id     = aws_secretsmanager_secret.oauth_initial.id
  secret_string = aws_secretsmanager_secret_version.oauth.secret_string
}

resource "aws_sagemaker_user_profile" "canvas" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-canvas-${random_pet.profile.id}"

  user_settings {
    execution_role = aws_iam_role.execution.arn
    canvas_app_settings {
      time_series_forecasting_settings {
        status = "DISABLED"
      }
      model_register_settings {
        status = "DISABLED"
      }
      direct_deploy_settings {
        status = "DISABLED"
      }
      kendra_settings {
        status = "DISABLED"
      }
      emr_serverless_settings {
        status = "DISABLED"
      }
      identity_provider_oauth_settings {
        data_source_name = "SalesforceGenie"
        secret_arn       = aws_secretsmanager_secret.oauth_initial.arn
        status           = "DISABLED"
      }
    }
  }
}
