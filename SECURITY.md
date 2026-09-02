# Security policy

Report security issues privately to the repository owner. Never commit credentials, OIDC secrets, database credentials, cookies, or Grafana state keys.

Runtime credentials are mounted from approved files. Native Grafana access is loopback-only, local and anonymous authentication are disabled, and datasource mutation is not authorized by this repository.
