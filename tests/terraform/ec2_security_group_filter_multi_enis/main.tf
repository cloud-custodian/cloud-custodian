resource "aws_instance" "primary_interface" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.primary_interface_public.id
  }

  network_interface {
    delete_on_termination = false
    device_index          = 1
    network_interface_id  = aws_network_interface.primary_interface_private.id
  }
}

resource "aws_network_interface" "primary_interface_public" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.public.id, ]
}

resource "aws_network_interface" "primary_interface_private" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.private.id, ]
}

resource "aws_instance" "secondary_interface" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.secondary_interface_private.id
  }

  network_interface {
    delete_on_termination = false
    device_index          = 1
    network_interface_id  = aws_network_interface.secondary_interface_public.id
  }
}

resource "aws_network_interface" "secondary_interface_public" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.public.id, ]
}

resource "aws_network_interface" "secondary_interface_private" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.private.id, ]
}

resource "aws_instance" "private_only_interface" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.private_only_interface.id
  }
}

resource "aws_network_interface" "private_only_interface" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.private.id, ]
}
