# Terraform module for IAM access key bad policy functional tests
# Creates IAM users for testing edge cases and error scenarios

# Generate unique name for empty user (user with no access keys)
resource "random_id" "empty_user" {
  prefix      = "c7n-test-user-empty-"
  byte_length = 4
}

# Create test user with no access keys (for testing empty user scenarios)
resource "aws_iam_user" "test_user_empty" {
  name = random_id.empty_user.hex
  path = "/c7n-test/"
}
