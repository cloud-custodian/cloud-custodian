# Terraform module for IAM access key good policy functional tests
# Creates IAM users with access keys for testing various filtering scenarios

# Generate unique names for test users to avoid conflicts
resource "random_id" "user1" {
  prefix      = "c7n-test-user-1-"
  byte_length = 4
}

resource "random_id" "user2" {
  prefix      = "c7n-test-user-2-"
  byte_length = 4
}

# Create test users
resource "aws_iam_user" "test_user_1" {
  name = random_id.user1.hex
  path = "/c7n-test/"
}

resource "aws_iam_user" "test_user_2" {
  name = random_id.user2.hex
  path = "/c7n-test/"
}

# Create access keys for test_user_1 (1 active, 1 inactive)
resource "aws_iam_access_key" "key_1_active" {
  user   = aws_iam_user.test_user_1.name
  status = "Active"
}

resource "aws_iam_access_key" "key_1_inactive" {
  user   = aws_iam_user.test_user_1.name
  status = "Inactive"
}

# Create access key for test_user_2 (1 active)
resource "aws_iam_access_key" "key_2_active" {
  user   = aws_iam_user.test_user_2.name
  status = "Active"
}
