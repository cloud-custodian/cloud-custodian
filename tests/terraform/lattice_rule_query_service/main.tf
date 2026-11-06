resource "aws_vpclattice_service" "test_service" {
  name      = "test-service"
  auth_type = "NONE"
}

resource "aws_vpclattice_listener" "test_listener" {
  name               = "test-listener"
  service_identifier = aws_vpclattice_service.test_service.id
  protocol           = "HTTP"
  port               = 80

  default_action {
    fixed_response {
      status_code = 404
    }
  }
}

resource "aws_vpclattice_listener_rule" "test_rule" {
  name                = "test-rule"
  service_identifier  = aws_vpclattice_service.test_service.id
  listener_identifier = aws_vpclattice_listener.test_listener.listener_id
  priority            = 10
  tags = {
    ExistingKey = "ExistingValue"
  }

  action {
    fixed_response {
      status_code = 404
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


resource "aws_vpclattice_service" "test_service2" {
  name      = "test-service2"
  auth_type = "NONE"
}

resource "aws_vpclattice_listener" "test_listener2" {
  name               = "test-listener2"
  service_identifier = aws_vpclattice_service.test_service2.id
  protocol           = "HTTP"
  port               = 80

  default_action {
    fixed_response {
      status_code = 404
    }
  }
}

resource "aws_vpclattice_listener_rule" "test_rule2" {
  name                = "test-rule2"
  service_identifier  = aws_vpclattice_service.test_service2.id
  listener_identifier = aws_vpclattice_listener.test_listener2.listener_id
  priority            = 10

  action {
    fixed_response {
      status_code = 404
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
