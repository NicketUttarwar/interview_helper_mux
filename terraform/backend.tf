# Committed local state: path is relative to this directory (terraform/).
# See terraform/README.md and docs/cross-cutting/podcast-rss-hosting.md —
# never commit config/terraform.tfvars or config/secrets/secrets.env.
terraform {
  backend "local" {
    path = "state/terraform.tfstate"
  }
}
