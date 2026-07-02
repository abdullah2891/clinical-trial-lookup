locals {
  pem_path = local_sensitive_file.private_key.filename
  ssh_base = "ssh -i ${local.pem_path} ubuntu@${aws_eip.app.public_ip}"
}

output "app_url" {
  description = "Public HTTPS URL of the application"
  value       = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "ec2_public_ip" {
  description = "EC2 Elastic IP"
  value       = aws_eip.app.public_ip
}

output "private_key_file" {
  description = "Path to the generated SSH private key (chmod 600 already set)"
  value       = local.pem_path
}

output "ssh_command" {
  description = "SSH into the EC2 instance"
  value       = local.ssh_base
}

output "logs_command" {
  description = "Tail all container logs"
  value       = "${local.ssh_base} 'cd /app && docker compose -f docker-compose.prod.yml logs -f'"
}

output "etl_command" {
  description = "One-time: load pgvector embeddings"
  value       = "${local.ssh_base} 'cd /app && docker compose -f docker-compose.prod.yml run --rm etl python -m etl.embedder'"
}
