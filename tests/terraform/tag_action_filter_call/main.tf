resource "aws_instance" "past_stop" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    "action_tag" = "This EC2 instance has had less than 5 percent CPU utilization for over 5 days: stop@2022/06/03"
  }
}

resource "aws_instance" "future_stop" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    "action_tag" = "This EC2 instance has had less than 5 percent CPU utilization for over 5 days: stop@9999/06/03"
  }
}

resource "aws_instance" "incorrect_month_stop" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    "action_tag" = "This EC2 instance has had less than 5 percent CPU utilization for over 5 days: stop@2022/33/03"
  }
}

resource "aws_instance" "incorrect_day_stop" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.example.id

  tags = {
    "action_tag" = "This EC2 instance has had less than 5 percent CPU utilization for over 5 days: stop@2022/06/33"
  }
}
