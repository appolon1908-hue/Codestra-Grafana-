from __future__ import annotations

import argparse
from pathlib import Path

import yaml


BUSINESSES = (
    "codestra",
    "moneybee",
    "beyvra",
    "breero",
    "larim-a",
    "transportation",
    "booked4seasons",
    "social",
    "klyrow",
    "telnexa",
    "kyqra",
    "restaurant",
    "provisioning",
)


def datasource_uid(signal: str, business: str) -> str:
    return f"codestra-{signal}-{business}"


def build() -> dict:
    datasources: list[dict] = [
        {
            "name": "Codestra Prometheus",
            "uid": "codestra-prometheus",
            "type": "prometheus",
            "access": "proxy",
            "url": "http://prometheus:9090",
            "isDefault": True,
            "editable": False,
            "jsonData": {
                "httpMethod": "POST",
                "manageAlerts": False,
                "prometheusType": "Prometheus",
                "prometheusVersion": "3.0.0",
                "cacheLevel": "High",
                "incrementalQuerying": True,
                "incrementalQueryOverlapWindow": "10m",
            },
        }
    ]
    for business in BUSINESSES:
        tempo_uid = datasource_uid("tempo", business)
        datasources.append(
            {
                "name": f"Codestra Tempo — {business}",
                "uid": tempo_uid,
                "type": "tempo",
                "access": "proxy",
                "url": "http://tempo:3200",
                "isDefault": False,
                "editable": False,
                "jsonData": {
                    "httpHeaderName1": "X-Scope-OrgID",
                    "serviceMap": {"datasourceUid": "codestra-prometheus"},
                    "nodeGraph": {"enabled": True},
                    "search": {"hide": False},
                    "traceQuery": {"timeShiftEnabled": True},
                },
                "secureJsonData": {"httpHeaderValue1": business},
            }
        )
        datasources.append(
            {
                "name": f"Codestra Loki — {business}",
                "uid": datasource_uid("loki", business),
                "type": "loki",
                "access": "proxy",
                "url": "http://loki:3100",
                "isDefault": False,
                "editable": False,
                "jsonData": {
                    "httpHeaderName1": "X-Scope-OrgID",
                    "maxLines": 1000,
                    "derivedFields": [
                        {
                            "name": "TraceID",
                            "matcherRegex": "(?:trace_id|traceID|traceId)[=\\\": ]+([a-fA-F0-9]{16,32})",
                            "datasourceUid": tempo_uid,
                            "url": "$${__value.raw}",
                            "urlDisplayLabel": "Open trace",
                        }
                    ],
                },
                "secureJsonData": {"httpHeaderValue1": business},
            }
        )
    return {"apiVersion": 1, "deleteDatasources": [], "prune": True, "datasources": datasources}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(build(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
