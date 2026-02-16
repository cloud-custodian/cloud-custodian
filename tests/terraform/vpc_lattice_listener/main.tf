provider "aws" {
  region = "us-east-1"
}

resource "aws_vpclattice_service" "example" {
  name = "c7n-lattice-service"
}

resource "aws_vpclattice_listener" "example" {
  name               = "c7n-lattice-listener"
  protocol           = "HTTP"
  service_identifier = aws_vpclattice_service.example.id

  default_action {
    fixed_response {
      status_code = 404
    }
  }

  tags = {
    Env = "Dev"
  }
}
