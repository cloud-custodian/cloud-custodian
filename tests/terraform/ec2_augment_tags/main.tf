resource "aws_instance" "tagged" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    Env   = "Production"
    Name  = "custodian-tester"
    Owner = "robot"
  }
}
