resource "aws_secretsmanager_secret" "this" {
  name = "secretsmanager_secret_string"
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id     = aws_secretsmanager_secret.this.id
  secret_string = "1234567890"
}
