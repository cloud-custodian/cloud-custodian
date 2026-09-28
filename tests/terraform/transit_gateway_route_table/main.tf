provider "aws" {
  region = "us-east-1"
}

resource "aws_ec2_transit_gateway" "example" {
  description = "Example Transit Gateway for Route Table Testing"

  tags = {
    Name = "c7n-test-tgw"
  }
}

# Create a VPC and attachment for associations/propagations
resource "aws_vpc" "test" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "c7n-test-vpc"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "test" {
  subnet_ids         = [aws_subnet.test.id]
  transit_gateway_id = aws_ec2_transit_gateway.example.id
  vpc_id             = aws_vpc.test.id

  tags = {
    Name = "c7n-test-attachment"
  }
}

resource "aws_subnet" "test" {
  vpc_id            = aws_vpc.test.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "c7n-test-subnet"
  }
}

resource "aws_ec2_transit_gateway_route_table" "available" {
  transit_gateway_id = aws_ec2_transit_gateway.example.id

  tags = {
    Name = "c7n-test-available-rt"
  }
}
