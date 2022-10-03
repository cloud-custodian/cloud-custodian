resource "aws_instance" "metadata_tags" {
  ami              = data.aws_ami.amazon_linux.id
  instance_type    = "t2.micro"
  subnet_id        = aws_subnet.example.id
  metadata_options = {}
}
