resource "aws_lb" "alb_waf_v2_assoc_missing" {
  name               = "alb-wafv2-assoc-missing"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.foo.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}

resource "aws_lb" "alb_waf_v2_ip_whitelisting_unallowed_addresses" {
  name               = "alb-wafv2-unallowed-addresses"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.foo.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}

resource "aws_lb" "alb_waf_v2_ip_whitelisting_allowed_addresses_only" {
  name               = "alb-wafv2-allowed-addresses-only"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.foo.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_2.id]
}
