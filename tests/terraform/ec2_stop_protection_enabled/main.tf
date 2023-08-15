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

resource "aws_instance" "stop_protection" {
  ami              = data.aws_ami.amazon_linux.id
  instance_type    = "t2.micro"
  subnet_id        = aws_subnet.example.id
  disable_api_stop = true
}
