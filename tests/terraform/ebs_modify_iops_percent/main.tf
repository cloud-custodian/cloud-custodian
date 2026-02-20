provider "aws" {
  region = "us-east-1"
}

resource "aws_ebs_volume" "test_volume" {
  availability_zone = "us-east-1a"
  size              = 8
  type              = "gp3"
  iops              = 3000

  tags = {
    Name = "modify_iops_percent_test_volume"
  }
}
