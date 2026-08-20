resource "random_pet" "api" {
  prefix = "example-api"
}

resource "aws_apigatewayv2_api" "example" {
  name                       = random_pet.api.id
  protocol_type              = "HTTP"
  route_selection_expression = "$request.method $request.path"
}

resource "aws_apigatewayv2_integration" "example" {
  api_id             = aws_apigatewayv2_api.example.id
  integration_type   = "HTTP_PROXY"
  integration_uri    = "https://example.com"
  integration_method = "ANY"
}

# Route with no authorization (should be flagged by policy)
resource "aws_apigatewayv2_route" "no_auth" {
  api_id             = aws_apigatewayv2_api.example.id
  route_key          = "GET /no-auth"
  target             = "integrations/${aws_apigatewayv2_integration.example.id}"
  authorization_type = "NONE"
}

# Route with IAM authorization (should pass policy)
resource "aws_apigatewayv2_route" "iam_auth" {
  api_id             = aws_apigatewayv2_api.example.id
  route_key          = "GET /iam-auth"
  target             = "integrations/${aws_apigatewayv2_integration.example.id}"
  authorization_type = "AWS_IAM"
}

