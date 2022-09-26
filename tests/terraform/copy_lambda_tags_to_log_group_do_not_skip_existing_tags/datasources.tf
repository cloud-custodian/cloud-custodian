data "archive_file" "lambda_package" {
  type        = "zip"
  output_path = "${path.module}/lambda_package.zip"

  source {
    content  = <<EOF
def lambda_handler(event, context):
  print('Hello from Lambda')
EOF
    filename = "${path.module}/handler.py"
  }
}