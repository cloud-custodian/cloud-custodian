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
}

resource "google_service_account" "c7n_test" {
  account_id = "c7n-kms-${random_pet.keyring.id}"
}

resource "google_kms_crypto_key_iam_member" "encrypter" {
  crypto_key_id = google_kms_crypto_key.c7n_test_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypter"
  member        = "serviceAccount:${google_service_account.c7n_test.email}"
}

resource "google_kms_crypto_key_iam_member" "decrypter" {
  crypto_key_id = google_kms_crypto_key.c7n_test_key.id
  role          = "roles/cloudkms.cryptoKeyDecrypter"
  member        = "serviceAccount:${google_service_account.c7n_test.email}"
}
