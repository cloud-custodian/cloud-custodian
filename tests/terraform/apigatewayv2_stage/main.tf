resource "random_pet" "api" {
  prefix = "example-api"
}

resource "aws_apigatewayv2_api" "example" {
  name                       = random_pet.api.id
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
}

resource "aws_apigatewayv2_stage" "example" {
  api_id = aws_apigatewayv2_api.example.id
  name   = random_pet.api.id

  tags = {
    Env = "Dev"
  }
}
