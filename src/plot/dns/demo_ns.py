"""Zones on the demo-ns nameservers that stand in for a hosting provider (D-012)."""

from collections.abc import Mapping, Sequence

import httpx

from plot.dns.pdns_client import fqdn

ZONE_TTL = 60


class DemoNsError(Exception):
    pass


class DemoNs:
    """Writes the same zone to every demo-ns instance through its pdns API."""

    def __init__(
        self,
        api_urls: Sequence[str],
        api_key: str,
        *,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.clients = [
            httpx.Client(
                base_url=f"{url.rstrip('/')}/api/v1/servers/localhost",
                headers={"X-API-Key": api_key},
                timeout=timeout,
                transport=transport,
            )
            for url in api_urls
        ]

    def ensure_zone(
        self, zone: str, nameservers: Sequence[str], a_records: Mapping[str, str]
    ) -> None:
        """Create or rewrite ``zone`` with apex NS ``nameservers`` and the given A records."""
        rrsets = [
            {
                "name": fqdn(zone),
                "type": "NS",
                "ttl": ZONE_TTL,
                "changetype": "REPLACE",
                "records": [{"content": fqdn(n), "disabled": False} for n in nameservers],
            }
        ] + [
            {
                "name": fqdn(name),
                "type": "A",
                "ttl": ZONE_TTL,
                "changetype": "REPLACE",
                "records": [{"content": address, "disabled": False}],
            }
            for name, address in sorted(a_records.items())
        ]
        for client in self.clients:
            try:
                found = client.get(f"/zones/{fqdn(zone)}")
                if found.status_code == 404:
                    response = client.post(
                        "/zones",
                        json={
                            "name": fqdn(zone),
                            "kind": "Native",
                            "nameservers": [fqdn(n) for n in nameservers],
                        },
                    )
                    _check(response)
                else:
                    _check(found)
                _check(client.patch(f"/zones/{fqdn(zone)}", json={"rrsets": rrsets}))
            except httpx.HTTPError as err:
                raise DemoNsError(f"demo-ns {client.base_url} unreachable: {err}") from err


def _check(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise DemoNsError(f"demo-ns API -> {response.status_code}: {response.text}")
