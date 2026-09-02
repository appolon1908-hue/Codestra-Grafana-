# Backup, restore, and rollback

Before deployment, capture the current image digest, configuration checksum, Compose manifest, provisioning state, and Grafana database backup. Prove the database backup is restorable outside production.

Rollback uses the previous approved digest without rebuilding, preserves the data volume, renders Compose first, and performs a controlled up operation. Never use docker compose down with volume deletion.
