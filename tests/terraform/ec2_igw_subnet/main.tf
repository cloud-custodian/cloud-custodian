resource "aws_instance" "public_auto_assigned" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = "t2.micro"
  subnet_id                   = aws_subnet.public.id
  associate_public_ip_address = true
}

resource "aws_instance" "private_auto_assigned" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = "t2.micro"
  subnet_id                   = aws_subnet.private.id
  associate_public_ip_address = false
}

resource "aws_instance" "public_primary_interface" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.public_primary_interface_public.id
  }

  network_interface {
    delete_on_termination = false
    device_index          = 1
    network_interface_id  = aws_network_interface.public_primary_interface_private.id
  }
}

resource "aws_network_interface" "public_primary_interface_public" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.this.id, ]
}

resource "aws_network_interface" "public_primary_interface_private" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.this.id, ]
}

resource "aws_instance" "public_secondary_interface" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.public_secondary_interface_private.id
  }

  network_interface {
    delete_on_termination = false
    device_index          = 1
    network_interface_id  = aws_network_interface.public_secondary_interface_public.id
  }
}

resource "aws_network_interface" "public_secondary_interface_public" {
  subnet_id       = aws_subnet.public.id
  security_groups = [aws_security_group.this.id, ]
}

resource "aws_network_interface" "public_secondary_interface_private" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.this.id, ]
}

resource "aws_instance" "private_interfacies_only" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interface {
    delete_on_termination = false
    device_index          = 0
    network_interface_id  = aws_network_interface.private_interfacies_only_1.id
  }

  network_interface {
    delete_on_termination = false
    device_index          = 1
    network_interface_id  = aws_network_interface.private_interfacies_only_2.id
  }
}

resource "aws_network_interface" "private_interfacies_only_1" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.this.id, ]
}

resource "aws_network_interface" "private_interfacies_only_2" {
  subnet_id       = aws_subnet.private.id
  security_groups = [aws_security_group.this.id, ]
}
