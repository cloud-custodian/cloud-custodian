resource "random_pet" "table" {
  prefix = "resolver-test"
  length = 2
}


resource "aws_dynamodb_table" "apps" {
  name         = random_pet.table.id
  hash_key     = "app_name"
  billing_mode = "PAY_PER_REQUEST"
  attribute {
    name = "app_name"
    type = "S"
  }
}


resource "aws_dynamodb_table_item" "app_cicd" {
  table_name = aws_dynamodb_table.apps.name
  hash_key   = aws_dynamodb_table.apps.hash_key

  item = <<ITEM
{
  "app_name": {"S": "cicd"},
  "env": {"S": "shared"}
}
ITEM
}

resource "aws_dynamodb_table_item" "app_app1" {
  table_name = aws_dynamodb_table.apps.name
  hash_key   = aws_dynamodb_table.apps.hash_key

  item = <<ITEM
{
  "app_name": {"S": "app1"},
  "env": {"S": "prod"}
}
ITEM
}