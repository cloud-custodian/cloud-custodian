provider "aws" {}

# Two minimal EC2 instances so we can test happy and sad paths.

resource "aws_instance" "test1" {
  ami           = "ami-01a4bfcb33649ac8e"
  instance_type = "t2.micro"
}

resource "aws_instance" "test2" {
  ami           = "ami-01a4bfcb33649ac8e"
  instance_type = "t2.micro"
}
