resource "aws_vpc_lattice_service" "test_service" {
  name      = "test-service"
  auth_type = "NONE"
}

resource "aws_vpc_lattice_listener" "test_listener" {
  name               = "test-listener"
  service_identifier = aws_vpc_lattice_service.test_service.id
  protocol           = "HTTP"
  port               = 80

  default_action {
    fixed_response {
      status_code = 200
    }
  }
}

resource "aws_vpc_lattice_rule" "test_rule" {
  name                = "test-rule"
  service_identifier  = aws_vpc_lattice_service.test_service.id
  listener_identifier = aws_vpc_lattice_listener.test_listener.id
  priority            = 10

  action {
    fixed_response {
      status_code = 200
    }
  }

  match {
    http_match {
      path_match {
        match {
          prefix = "/"
        }
      }
    }
  }
}
