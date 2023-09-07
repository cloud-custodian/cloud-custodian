resource "random_pet" "server" {
}

data "google_kms_key_ring" "c7n" {
  name     = "keyring-c7n"
  location = "us-central1"
}

resource "google_kms_key_ring" "c7n" {
  count    = data.google_kms_key_ring.c7n.id != null ? 0 : 1
  name     = "keyring-c7n"
  location = "us-central1"
}

resource "google_kms_crypto_key" "c7n" {
  name     = "keyname-${random_pet.server.id}-c7n"
  key_ring = data.google_kms_key_ring.c7n.id != null ? data.google_kms_key_ring.c7n.id : google_kms_key_ring.c7n[0].id
}