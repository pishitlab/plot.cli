"""PowerDNS Authoritative HTTP API client for the registry zone ``.`` (SPEC §7.1).

Checked against powerdns/pdns-auth-49:4.9.17 (see PROGRESS "Pinned versions"):
the root zone's API id is ``=2E``; ``soa_edit_api=INCREASE`` bumps the serial on every
PATCH (``INCEPTION-INCREMENT`` does not); DELETE of an absent RRset succeeds.
"""

from typing import Any

import httpx

from plot.dns.projector import Snapshot

ROOT_ZONE_ID = "=2E"
ROOT_NS = "a.root-servers.net"
SOA_EDIT_API = "INCREASE"
ROOT_TTL = 3600
SOA_TTL = 300
SOA_MINIMUM = 5  # short negative caching (SPEC §7.1)


class PdnsError(Exception):
    pass


def fqdn(name: str) -> str:
    return name if name.endswith(".") else name + "."


def _rrset(name: str, rtype: str, ttl: int, contents: list[str]) -> dict[str, Any]:
    return {
        "name": fqdn(name),
        "type": rtype,
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": c, "disabled": False} for c in contents],
    }


def _delete(name: str, rtype: str) -> dict[str, Any]:
    return {"name": fqdn(name), "type": rtype, "changetype": "DELETE"}


def rrset_changes(domain: str, old: Snapshot, new: Snapshot) -> list[dict[str, Any]]:
    """RRset operations turning the zone's data for ``domain`` from ``old`` into ``new``."""
    changes: list[dict[str, Any]] = []
    if new is not None and new["nameservers"]:
        changes.append(_rrset(domain, "NS", new["ttl"], [fqdn(n) for n in new["nameservers"]]))
    else:
        changes.append(_delete(domain, "NS"))
    new_glue: dict[str, dict[str, list[str]]] = new["glue"] if new is not None else {}
    old_glue: dict[str, dict[str, list[str]]] = old["glue"] if old is not None else {}
    for host in sorted(set(old_glue) | set(new_glue)):
        for rtype in ("A", "AAAA"):
            addresses = new_glue.get(host, {}).get(rtype, [])
            if addresses and new is not None:
                changes.append(_rrset(host, rtype, new["ttl"], addresses))
            else:
                changes.append(_delete(host, rtype))
    return changes


def root_rrsets(root_ip: str) -> list[dict[str, Any]]:
    soa = f"{ROOT_NS}. hostmaster.sandbox.invalid. 1 1800 900 604800 {SOA_MINIMUM}"
    return [
        _rrset(".", "SOA", SOA_TTL, [soa]),
        _rrset(".", "NS", ROOT_TTL, [f"{ROOT_NS}."]),
        _rrset(ROOT_NS, "A", ROOT_TTL, [root_ip]),
    ]


def _root_drift(
    current: list[dict[str, Any]], wanted: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Root records that differ from ``wanted``. The SOA serial is ignored and kept, so it
    only ever grows (pdns bumps it on each PATCH)."""
    have = {(r["name"], r["type"]): r for r in current}
    ops = []
    for want in wanted:
        got = have.get((want["name"], want["type"]))
        contents = [rec["content"] for rec in want["records"]]
        if got is not None and want["type"] == "SOA":
            fields = got["records"][0]["content"].split() if got["records"] else []
            if len(fields) == 7:
                serial_kept = contents[0].split()
                serial_kept[2] = fields[2]
                contents = [" ".join(serial_kept)]
        same = (
            got is not None
            and got["ttl"] == want["ttl"]
            and sorted(r["content"] for r in got["records"]) == sorted(contents)
        )
        if not same:
            ops.append(_rrset(want["name"], want["type"], want["ttl"], contents))
    return ops


class PdnsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        server_id: str = "localhost",
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._server_url = f"{base_url.rstrip('/')}/api/v1/servers/{server_id}"
        self._http = httpx.Client(
            base_url=self._server_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def ping(self) -> bool:
        try:
            # the server resource has no trailing slash (".../localhost/" is a 404)
            return self._http.get(self._server_url).status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_root_zone(self, root_ip: str) -> None:
        """Create zone ``.`` if missing, then (re)write its SOA, NS and root server A."""
        response = self._request("GET", f"/zones/{ROOT_ZONE_ID}", allow_404=True)
        if response.status_code == 404:
            self._request(
                "POST",
                "/zones",
                json={
                    "name": ".",
                    "kind": "Native",
                    "nameservers": [],
                    "soa_edit_api": SOA_EDIT_API,
                    "rrsets": [
                        {k: v for k, v in r.items() if k != "changetype"}
                        for r in root_rrsets(root_ip)
                    ],
                },
            )
            return
        zone = response.json()
        if zone.get("soa_edit_api") != SOA_EDIT_API:
            self._request("PUT", f"/zones/{ROOT_ZONE_ID}", json={"soa_edit_api": SOA_EDIT_API})
        self.patch(_root_drift(zone.get("rrsets", []), root_rrsets(root_ip)))

    def zone_rrsets(self) -> list[dict[str, Any]]:
        rrsets: list[dict[str, Any]] = self._request("GET", f"/zones/{ROOT_ZONE_ID}").json()[
            "rrsets"
        ]
        return rrsets

    def patch(self, rrsets: list[dict[str, Any]]) -> None:
        if rrsets:
            self._request("PATCH", f"/zones/{ROOT_ZONE_ID}", json={"rrsets": rrsets})

    def apply(self, domain: str, old: Snapshot, new: Snapshot) -> None:
        self.patch(rrset_changes(domain, old, new))

    def _request(
        self, method: str, path: str, *, json: Any = None, allow_404: bool = False
    ) -> httpx.Response:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.HTTPError as err:
            raise PdnsError(f"pdns API unreachable: {err}") from err
        if response.status_code >= 400 and not (allow_404 and response.status_code == 404):
            raise PdnsError(f"pdns API {method} {path} -> {response.status_code}: {response.text}")
        return response
