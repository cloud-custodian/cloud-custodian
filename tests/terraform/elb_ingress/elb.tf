resource "aws_lb" "alb_unallowed" {
  name               = "alb-unallowed"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.unallowed.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}

resource "aws_lb" "alb_allowed" {
  name               = "alb-allowed"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.allowed.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}

resource "aws_lb" "nlb_unallowed" {
  name               = "nlb-unallowed"
  load_balancer_type = "network"
  security_groups    = [aws_security_group.unallowed.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}

resource "aws_lb" "nlb_allowed" {
  name               = "nlb-allowed"
  load_balancer_type = "network"
  security_groups    = [aws_security_group.allowed.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}
