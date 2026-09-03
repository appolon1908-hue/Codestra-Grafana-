# Upgrade policy

Select an official Grafana release, resolve its tag to an exact Git commit and multi-platform image digest, and verify the linux/amd64 manifest and binary version. Update the runtime lock and build manifest together on a feature branch.

Build and scan the derived image in CI. Promote only the same protected source and immutable digest through test, staging, production, and main.
