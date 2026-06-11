provider "aws" {
  region = "us-east-1"
}

resource "aws_vpc" "main" {
  cidr_block       = "10.0.0.0/16"
  instance_tenancy = "default"

  tags = {
    Name = "c7n-test"
  }
}

resource "aws_subnet" "main" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "c7n-test"
  }
}

resource "aws_security_group" "main" {
  name_prefix = "c7n-test"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "c7n-test"
  }
}

resource "aws_vpc_endpoint" "main" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.us-east-1.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.main.id]
  security_group_ids  = [aws_security_group.main.id]
  private_dns_enabled = true

  tags = {
    Name = "c7n-test"
  }
}
