# El compadre: EC2 con Airflow y dbt en Docker. Solo mi IP entra por SSH (22) y Airflow (8080).

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}

# Solo se sube la llave PUBLICA. La privada nunca sale del PC.
resource "aws_key_pair" "la_llave" {
  key_name   = "la-llave-dw"
  public_key = file(pathexpand(var.llave_publica))
}

resource "aws_instance" "compadre" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.clase
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [var.security_group_id]
  key_name                    = aws_key_pair.la_llave.key_name
  iam_instance_profile        = var.instance_profile
  associate_public_ip_address = true

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = true

  metadata_options {
    http_tokens                 = "required" # IMDSv2
    http_put_response_hop_limit = 2          # los contenedores de Docker necesitan el segundo salto para leer las credenciales del rol
  }

  root_block_device {
    volume_size = var.disco_gb
    volume_type = "gp3"
  }

  # Evita que una imagen nueva de Amazon Linux reemplace al compadre y borre lo que tenga adentro.
  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = { Name = "el-compadre-dw" }
}
