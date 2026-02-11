resource "random_pet" "network" {
  prefix = "c7n-test-network"
}

resource "aws_vpclattice_service_network" "test" {
  name = random_pet.network.id

  tags = {
    Environment = "Test"
    ASV         = "PolicyTestASV"
  }
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_vpclattice_service_network_vpc_association" "test" {
  service_network_identifier = aws_vpclattice_service_network.test.id
  vpc_identifier             = data.aws_vpc.default.id

  tags = {
    Environment = "Test"
    ASV         = "PolicyTestASV"
  }
}
