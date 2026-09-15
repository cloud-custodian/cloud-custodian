locals {
  tags = {
    Env   = "Production"
    Name  = "custodian-tester"
    Owner = "robot"
  }
}

# Two instances: one is enough for the by-id lookup, the second exercises the
# fall back to a region-wide filter (with the ceiling patched down in tests).
resource "aws_instance" "tagged_a" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
  tags          = local.tags
}

resource "aws_instance" "tagged_b" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
  tags          = local.tags
}
