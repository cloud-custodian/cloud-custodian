# Amazon-owned AMI (public, owned by amazon)
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# Local AMI copy (stays available throughout test)
resource "aws_ami_copy" "local_ami" {
  name              = "test-local-ami"
  source_ami_id     = data.aws_ami.amazon_linux.id
  source_ami_region = "us-east-1"
}

# Local AMI copy that will be deregistered after the instance launches
resource "aws_ami_copy" "deregistered_ami_source" {
  name              = "test-deregistered-ami"
  source_ami_id     = data.aws_ami.amazon_linux.id
  source_ami_region = "us-east-1"
}
