resource "aws_vpc" "msk" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "msk-test-vpc-${random_id.id.hex}"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "msk" {
  count = 2

  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(aws_vpc.msk.cidr_block, 8, count.index)
  vpc_id            = aws_vpc.msk.id

  tags = {
    Name = "msk-test-subnet-${count.index}-${random_id.id.hex}"
  }
}

resource "aws_security_group" "msk" {
  name_prefix = "msk-test-sg-"
  vpc_id      = aws_vpc.msk.id

  ingress {
    from_port   = 9092
    to_port     = 9098
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.msk.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "msk-test-sg-${random_id.id.hex}"
  }
}

