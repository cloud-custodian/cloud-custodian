resource "aws_ssm_patch_baseline" "production" {
  name             = "patch-baseline"
  approved_patches = ["KB123456"]
}

resource "aws_ssm_patch_group" "patchgroup" {
  baseline_id = aws_ssm_patch_baseline.production.id
  patch_group = "patch-group-name"
}
