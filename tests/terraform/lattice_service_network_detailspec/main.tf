resource "aws_vpclattice_service_network" "test" {
  name      = "test-lattice-network"
  auth_type = "AWS_IAM"
  tags = {
    TestServiceNetwork = "TestServiceNetworkValue"
  }
}