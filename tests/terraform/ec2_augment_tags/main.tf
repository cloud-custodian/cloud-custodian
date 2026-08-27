resource "aws_instance" "tagged_a" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    Env   = "Production"
    Name  = "custodian-tester"
    Owner = "robot"
  }
}

resource "aws_instance" "tagged_b" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    Env   = "Production"
    Name  = "custodian-tester"
    Owner = "robot"
  }
}

# No tags: probes whether describe_instances omits Tags or returns [].
resource "aws_instance" "untagged" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
}
