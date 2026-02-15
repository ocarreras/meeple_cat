output "server_ip" {
  description = "Public IPv4 of the Hetzner server"
  value       = hcloud_server.meeple.ipv4_address
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh root@${hcloud_server.meeple.ipv4_address}"
}

output "kubeconfig_command" {
  description = "Command to fetch kubeconfig from the server"
  value       = "scp root@${hcloud_server.meeple.ipv4_address}:/etc/rancher/k3s/k3s.yaml ~/.kube/meeple-config"
}
