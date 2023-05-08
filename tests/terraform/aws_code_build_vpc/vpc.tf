resource "aws_vpc" "example" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Env = "Dev"
  }
}

resource "aws_subnet" "example" {
  vpc_id            = aws_vpc.example.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}
