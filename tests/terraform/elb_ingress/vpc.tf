resource "aws_vpc" "this" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "subnet_1" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "subnet_2" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_security_group" "unallowed" {
  vpc_id = aws_vpc.this.id
  name   = "unallowed"
}

resource "aws_vpc_security_group_ingress_rule" "unallowed" {
  security_group_id = aws_security_group.unallowed.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_security_group" "allowed" {
  vpc_id = aws_vpc.this.id
  name   = "allowed"
}

resource "aws_vpc_security_group_ingress_rule" "allowed" {
  security_group_id = aws_security_group.allowed.id
  cidr_ipv4         = "192.168.0.0/28"
  ip_protocol       = "-1"
}
