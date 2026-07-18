provider "google" {}

resource "random_pet" "keyring" {
  length = 1
}

resource "google_kms_key_ring" "c7n_test" {
  name     = "c7n-test-keyring-${random_pet.keyring.id}"
  location = "us-central1"
}

resource "google_kms_crypto_key" "c7n_test_key" {
  name     = "c7n-test-cryptokey"
  key_ring = google_kms_key_ring.c7n_test.id
  purpose  = "ENCRYPT_DECRYPT"

  labels = {
    env = "default"
  }
}

