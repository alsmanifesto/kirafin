output "api_url" {
  description = "HTTPS URL of the Payments API"
  value       = "https://${aws_lb.main.dns_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}
