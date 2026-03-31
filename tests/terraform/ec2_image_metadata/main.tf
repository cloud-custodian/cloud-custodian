# Instance using Amazon-owned AMI
resource "aws_instance" "amazon_ami" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
}

# Instance using local (account-owned) AMI copy — stays available
resource "aws_instance" "local_ami" {
  ami           = aws_ami_copy.local_ami.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
}

# Instance using local AMI copy that gets deregistered after launch
resource "aws_instance" "deregistered_ami" {
  ami           = aws_ami_copy.deregistered_ami_source.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id
}

# Deregister the AMI after the instance is running
resource "null_resource" "deregister_ami" {
  depends_on = [aws_instance.deregistered_ami]

  provisioner "local-exec" {
    command = "aws ec2 deregister-image --image-id ${aws_ami_copy.deregistered_ami_source.id} --region us-east-1"
  }
}
