resource "aws_default_route_table" "example" {
  default_route_table_id = aws_vpc.example.default_route_table_id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.example.id
  }
}

resource "aws_vpc" "example" {
  cidr_block = "10.0.0.0/16"
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "cluster_example" {
  count = 2

  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.example.cidr_block, 8, count.index)
  vpc_id                  = aws_vpc.example.id
  map_public_ip_on_launch = true
}

resource "aws_subnet" "node_group_example" {
  count = 2

  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.example.cidr_block, 8, count.index + 2)
  vpc_id                  = aws_vpc.example.id
  map_public_ip_on_launch = true

  tags = {
    "kubernetes.io/cluster/${aws_eks_cluster.example.name}" = "shared"
  }
}

resource "aws_internet_gateway" "example" {
  vpc_id = aws_vpc.example.id
}
