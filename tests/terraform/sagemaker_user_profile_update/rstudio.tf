resource "aws_sagemaker_user_profile" "rstudio" {
  domain_id         = aws_sagemaker_domain.main.id
  user_profile_name = "c7n-rstudio-${random_pet.profile.id}"

  user_settings {
    execution_role = aws_iam_role.execution.arn
    r_studio_server_pro_app_settings {
      access_status = "DISABLED"
    }
  }
}
