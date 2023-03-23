data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}


data "aws_availability_zones" "available" {
  state = "available"
}


resource "aws_launch_template" "foobar" {
  name_prefix   = "foobar"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t3.medium"
}

resource "aws_autoscaling_group" "bar" {
  availability_zones = [data.aws_availability_zones.available.names[0]]
  desired_capacity   = 1
  max_size           = 1
  min_size           = 1

  launch_template {
    id      = aws_launch_template.foobar.id
    version = "$Latest"
  }
  tag {
    key                 = "App"
    value               = "Testing"
    propagate_at_launch = true
  }
}
