resource "aws_instance" "no_protection" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
}

resource "aws_instance" "termination_protection" {
  ami                     = data.aws_ami.amazon_linux.id
  instance_type           = "t2.micro"
  subnet_id               = aws_subnet.example.id
  disable_api_termination = true
}

resource "terraform_data" "remove_termination_protection" {
  input = aws_instance.termination_protection.id

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      aws ec2 modify-instance-attribute \
        --instance-id ${self.output} \
        --no-disable-api-termination
    EOT
  }
}

resource "aws_instance" "stop_protection" {
  ami              = data.aws_ami.amazon_linux.id
  instance_type    = "t2.micro"
  subnet_id        = aws_subnet.example.id
  disable_api_stop = true
}

resource "terraform_data" "remove_stop_protection" {
  input = aws_instance.stop_protection.id

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      aws ec2 modify-instance-attribute \
        --instance-id ${self.output} \
        --no-disable-api-stop
    EOT
  }
}
