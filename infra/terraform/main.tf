terraform {
  required_version = ">= 1.5"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "aws" {
  region = "eu-central-1"
}

# ── SSH Key ──────────────────────────────────────────────────

resource "hcloud_ssh_key" "meeple" {
  name       = "meeple-deploy"
  public_key = file(var.ssh_public_key_path)
}

# ── Firewall ─────────────────────────────────────────────────

resource "hcloud_firewall" "meeple" {
  name = "meeple-fw"

  rule {
    description = "SSH"
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTP"
    direction   = "in"
    protocol    = "tcp"
    port        = "80"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTPS"
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "Kubernetes API"
    direction   = "in"
    protocol    = "tcp"
    port        = "6443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }
}

# ── Server ───────────────────────────────────────────────────

resource "hcloud_server" "meeple" {
  name         = "meeple"
  image        = "ubuntu-24.04"
  server_type  = var.server_type
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.meeple.id]
  firewall_ids = [hcloud_firewall.meeple.id]

  user_data = <<-EOT
    #!/bin/bash
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive

    apt-get update && apt-get upgrade -y

    # Install k3s with TLS SAN for remote kubectl access
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--tls-san ${var.domain}" sh -

    # Wait for k3s to be ready
    until kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done

    # Install cert-manager for automatic TLS
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.3/cert-manager.yaml

    # Install Helm
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

    echo "k3s setup complete" > /root/.k3s-ready
  EOT

  connection {
    type        = "ssh"
    user        = "root"
    private_key = file(var.ssh_private_key_path)
    host        = self.ipv4_address
  }

  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait",
      "until [ -f /root/.k3s-ready ]; do sleep 5; done",
      "echo 'k3s is ready'",
    ]
  }
}

# ── DNS (Route 53) ───────────────────────────────────────────

resource "aws_route53_record" "meeple" {
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [hcloud_server.meeple.ipv4_address]
}
