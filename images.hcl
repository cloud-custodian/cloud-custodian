variable "DOCKER_PUSH" {
  description = "Set to 'true' to push the built images, or 'false' to build locally."
  default     = "false"
}

variable "DOCKER_PLATFORMS" {
  description = "Comma separated list of platforms to build the image for. Example: linux/amd64,linux/arm64"
  default     = "linux/arm64"
}

variable "DOCKER_REGISTRY" {
  description = "The registry URL where the images will be pushed."
  default     = "304971447450.dkr.ecr.eu-west-3.amazonaws.com"
}
variable "CUSTODIAN_VERSION" {
  description = "The version of Cloud Custodian to build."
  default     = "mm-0.9.46.0"
}

group "default" {
  targets = ["c7n-kube", "c7n-org"]
}

target "template" {
  context = "./"
  platforms = split(",", "${DOCKER_PLATFORMS}")
  output    = [equal(DOCKER_PUSH, "true") ? "type=registry,push=true,oci-mediatypes=true,compression=zstd" : "type=image,oci-mediatypes=true,compression=zstd"]
}

target "c7n-kube" {
  inherits   = ["template"]
  dockerfile = "docker/c7n-kube"
  # XXX Should be tagged c7n-kube
  tags       = ["${DOCKER_REGISTRY}/public/cloudcustodian/c7n:${CUSTODIAN_VERSION}"]
}

target "c7n-org" {
  inherits   = ["template"]
  dockerfile = "docker/c7n-org"
  tags       = ["${DOCKER_REGISTRY}/public/cloudcustodian/c7n-org:${CUSTODIAN_VERSION}"]
}
