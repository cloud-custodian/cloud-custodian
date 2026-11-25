resource "aws_iam_role" "updated_execution" {
  name               = "c7n-profile-updated-${random_pet.profile.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_security_group" "initial" {
  name_prefix = "c7n-profile-initial-"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_security_group" "updated" {
  name_prefix = "c7n-profile-updated-"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_s3_bucket" "sharing" {
  bucket_prefix = "c7n-profile-sharing-"
  force_destroy = true
}

resource "aws_kms_key" "sharing" {
  description             = "SageMaker profile update test"
  deletion_window_in_days = 7
}

resource "aws_sagemaker_user_profile" "settings" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-settings-${random_pet.profile.id}"

  user_settings {
    execution_role      = aws_iam_role.execution.arn
    security_groups     = [aws_security_group.initial.id]
    default_landing_uri = "app:JupyterServer:"
    studio_web_portal   = "ENABLED"
    auto_mount_home_efs = "DefaultAsDomain"

    sharing_settings {
      notebook_output_option = "Disabled"
    }

    space_storage_settings {
      default_ebs_storage_settings {
        default_ebs_volume_size_in_gb = 5
        maximum_ebs_volume_size_in_gb = 20
      }
    }

    studio_web_portal_settings {
      hidden_app_types      = ["Canvas"]
      hidden_instance_types = ["ml.g5.xlarge"]
      hidden_ml_tools       = ["Experiments"]
    }
  }
}
