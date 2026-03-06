variable "ecr_url" {
  description = "ECR repository URL (created by pipeline before terraform apply)"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name, used as prefix for all resources"
  type        = string
  default     = "payments-api"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "image_tag" {
  description = "Docker image tag to deploy (set by CI/CD to git SHA)"
  type        = string
}

variable "blockchain_service_url" {
  description = "URL of the blockchain confirmation service"
  type        = string
  default     = "http://mock-blockchain:8001"
}

variable "desired_count" {
  description = "Number of ECS task replicas"
  type        = number
  default     = 2
}
