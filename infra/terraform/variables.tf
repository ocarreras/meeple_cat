variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key"
  type        = string
  default     = "~/.ssh/meeple-hetzner.pub"
}

variable "ssh_private_key_path" {
  description = "Path to SSH private key (for remote-exec provisioner)"
  type        = string
  default     = "~/.ssh/meeple-hetzner"
}

variable "server_type" {
  description = "Hetzner server type"
  type        = string
  default     = "cx33"
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "nbg1"
}

variable "domain" {
  description = "Domain for the application"
  type        = string
  default     = "play.meeple.cat"
}

variable "route53_zone_id" {
  description = "AWS Route 53 hosted zone ID"
  type        = string
  default     = "Z037706987H9NU6DCOBE"
}
