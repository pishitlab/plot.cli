"""Scenario engine (SPEC §10): YAML steps against the API, expectations against DNS.

A scenario file holds ``id``, ``name``, ``description``, ``domains`` (placeholders) and
``steps``. Each step is one action:

- ``api: {method, path, body}`` with ``expect: {status, code, json}``
- ``verify: {domain, expect: [ns...], status, within, elapsed: {min, max}}``
- ``dns: {server: resolver|registry, name, type, rcode, answers, glue, within}``
- ``provider_zone: {domain, on: [demo-ns1, ...], nameservers, records: {label: ip}}``
- ``mark: <label>`` starts the clock that ``elapsed`` is measured from

``${a}`` expands to the scenario's random ``scn-`` domain for placeholder ``a``;
``${a:upper}`` to its upper-case form; other names come from the engine's ``variables``
(``lame_ip``: an address nothing answers on, ``demo_ns1_ip``/``demo_ns2_ip``).
Every run ends with cleanup: settings restored, ``scn-`` data reset, demo-ns zones removed.
"""

import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from plot.cli.client import ApiClient, ApiError
from plot.verifier.verify import DnsProbe, verify

PREFIX = "scn-"
DEFAULT_VARIABLES = {
    "lame_ip": "172.28.0.99",
    "demo_ns1_ip": "172.28.0.31",
    "demo_ns2_ip": "172.28.0.32",
}
DEFAULT_WITHIN = 0.0
POLL_INTERVAL = 0.5


class ScenarioError(Exception):
    pass


# --- file format -------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiCall(_Model):
    method: str
    path: str
    body: Any = None


class ApiExpect(_Model):
    status: int | None = None
    code: str | None = None
    json_: dict[str, Any] | None = Field(default=None, alias="json")


class VerifyCall(_Model):
    domain: str
    expect: list[str]
    status: str
    within: float = DEFAULT_WITHIN
    elapsed: dict[str, float] | None = None


class DnsCall(_Model):
    server: str = "resolver"
    name: str
    type: str
    rcode: str | None = None
    answers: list[str] | None = None
    glue: list[str] | None = None
    within: float = DEFAULT_WITHIN


class ZoneCall(_Model):
    domain: str
    on: list[str] | None = None
    nameservers: list[str] = ["ns1.myhost.net", "ns2.myhost.net"]
    records: dict[str, str] = {}


class Step(_Model):
    title: str | None = None
    api: ApiCall | None = None
    expect: ApiExpect | None = None
    verify: VerifyCall | None = None
    dns: DnsCall | None = None
    provider_zone: ZoneCall | None = None
    mark: str | None = None

    @model_validator(mode="after")
    def one_action(self) -> "Step":
        actions = [
            k
            for k in ("api", "verify", "dns", "provider_zone", "mark")
            if getattr(self, k) is not None
        ]
        if len(actions) != 1:
            raise ValueError(f"a step needs exactly one action, got {actions or 'none'}")
        if self.expect is not None and self.api is None:
            raise ValueError("'expect' belongs to an 'api' step")
        return self

    @property
    def kind(self) -> str:
        return next(
            k
            for k in ("api", "verify", "dns", "provider_zone", "mark")
            if getattr(self, k) is not None
        )


class Scenario(_Model):
    id: str
    name: str
    description: str
    domains: list[str] = []
    steps: list[Step]


def load_scenario(path: Path) -> Scenario:
    try:
        return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (ValidationError, yaml.YAMLError) as err:
        raise ScenarioError(f"{path.name}: {err}") from err


def load_catalog(directory: Path | None = None) -> dict[str, Scenario]:
    root = directory or Path(str(resources.files("plot.scenarios") / "catalog"))
    scenarios = [load_scenario(p) for p in sorted(root.glob("*.yml"))]
    catalog = {s.id: s for s in scenarios}
    if len(catalog) != len(scenarios):
        raise ScenarioError("duplicate scenario id in catalog")
    return catalog


# --- what the engine talks to ----------------------------------------------------------


@dataclass(frozen=True)
class DnsAnswer:
    rcode: str
    answers: list[str]
    glue: list[str]


class ScenarioDns(Protocol):
    def ask(self, server: str, name: str, rtype: str) -> DnsAnswer: ...


class Zones(Protocol):
    def ensure_zone(
        self, zone: str, nameservers: list[str], a_records: dict[str, str], on: list[str] | None
    ) -> None: ...

    def delete_zone(self, zone: str) -> None: ...


@dataclass
class StepResult:
    index: int
    kind: str
    title: str
    ok: bool
    detail: str
    seconds: float


@dataclass
class ScenarioResult:
    id: str
    name: str
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    seconds: float = 0.0
    cleanup_error: str | None = None


class StepFailed(Exception):
    pass


class Engine:
    def __init__(
        self,
        api: ApiClient,
        verifier_dns: DnsProbe,
        dns: ScenarioDns,
        zones: Zones | None,
        *,
        variables: dict[str, str] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api = api
        self.verifier_dns = verifier_dns
        self.dns = dns
        self.zones = zones
        self.variables = {**DEFAULT_VARIABLES, **(variables or {})}
        self.monotonic = monotonic
        self.sleep = sleep

    def run(self, scenario: Scenario) -> ScenarioResult:
        names = {
            key: f"{PREFIX}{scenario.id.lower()}-{key}-{secrets.token_hex(3)}.com"
            for key in scenario.domains
        }
        result = ScenarioResult(scenario.id, scenario.name, passed=True)
        started = self.monotonic()
        state = _RunState(names=names, mark=started)
        saved_settings = self.api.get("/admin/settings")
        try:
            for index, raw in enumerate(scenario.steps, start=1):
                step = Step.model_validate(
                    _expand(
                        raw.model_dump(by_alias=True, exclude_none=True),
                        {**self.variables, **names},
                    )
                )
                step_started = self.monotonic()
                try:
                    detail = self._run_step(step, state)
                    ok = True
                except (StepFailed, ApiError) as err:
                    detail, ok = str(err), False
                result.steps.append(
                    StepResult(
                        index,
                        step.kind,
                        step.title or step.kind,
                        ok,
                        detail,
                        self.monotonic() - step_started,
                    )
                )
                if not ok:
                    result.passed = False
                    break
        finally:
            result.cleanup_error = self._cleanup(saved_settings, state)
            result.seconds = self.monotonic() - started
        return result

    # steps ------------------------------------------------------------------------

    def _run_step(self, step: Step, state: "_RunState") -> str:
        if step.mark is not None:
            state.mark = self.monotonic()
            return f"clock started ({step.mark})"
        if step.api is not None:
            return self._api(step.api, step.expect or ApiExpect())
        if step.verify is not None:
            return self._verify(step.verify, state)
        if step.dns is not None:
            return self._dns(step.dns)
        assert step.provider_zone is not None
        return self._zone(step.provider_zone, state)

    def _api(self, call: ApiCall, expect: ApiExpect) -> str:
        status, body = self.api.call(call.method.upper(), call.path, json=call.body)
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        if expect.code is not None and code != expect.code:
            raise StepFailed(f"expected error {expect.code}, got {code or f'HTTP {status}'}")
        if expect.status is not None and status != expect.status:
            raise StepFailed(f"expected HTTP {expect.status}, got {status} ({code or 'no error'})")
        if expect.code is None and expect.status is None and status >= 400:
            raise StepFailed(f"unexpected HTTP {status} {code or ''}".rstrip())
        if expect.json_ is not None:
            mismatch = _subset_mismatch(expect.json_, body)
            if mismatch:
                raise StepFailed(f"response {mismatch}")
        return f"{call.method.upper()} {call.path} -> {status}{f' {code}' if code else ''}"

    def _verify(self, call: VerifyCall, state: "_RunState") -> str:
        last = self._poll(
            lambda: (
                verify(
                    call.domain, call.expect, self.verifier_dns, self.api.is_registered
                ).status.value
            ),
            lambda status: status == call.status,
            call.within,
        )
        if last != call.status:
            raise StepFailed(
                f"verifier said {last}, expected {call.status} (within {call.within}s)"
            )
        elapsed = self.monotonic() - state.mark
        if call.elapsed is not None:
            low, high = call.elapsed.get("min", 0.0), call.elapsed.get("max", float("inf"))
            if not low <= elapsed <= high:
                raise StepFailed(f"{call.status} after {elapsed:.1f}s, expected {low}-{high}s")
        return f"{call.status} after {elapsed:.1f}s"

    def _dns(self, call: DnsCall) -> str:
        def matches(answer: DnsAnswer) -> bool:
            return (
                (call.rcode is None or answer.rcode == call.rcode)
                and (call.answers is None or sorted(answer.answers) == sorted(call.answers))
                and (call.glue is None or sorted(answer.glue) == sorted(call.glue))
            )

        answer = self._poll(
            lambda: self.dns.ask(call.server, call.name, call.type), matches, call.within
        )
        if not matches(answer):
            raise StepFailed(
                f"{call.server} {call.name} {call.type}: rcode={answer.rcode} "
                f"answers={answer.answers} glue={answer.glue}"
            )
        return f"{call.server} {call.name} {call.type}: {answer.rcode} {answer.answers}"

    def _zone(self, call: ZoneCall, state: "_RunState") -> str:
        if self.zones is None:
            raise StepFailed("demo-ns is not configured (set DEMO_NS_API_URLS and PDNS_API_KEY)")
        records = {
            f"{label}.{call.domain}" if label != "@" else call.domain: ip
            for label, ip in call.records.items()
        }
        self.zones.ensure_zone(call.domain, call.nameservers, records, call.on)
        state.zones.add(call.domain)
        return f"zone {call.domain} on {', '.join(call.on or ['all demo-ns'])}"

    # helpers ----------------------------------------------------------------------

    def _poll(self, probe: Callable[[], Any], done: Callable[[Any], bool], within: float) -> Any:
        deadline = self.monotonic() + within
        while True:
            value = probe()
            if done(value) or self.monotonic() >= deadline:
                return value
            self.sleep(POLL_INTERVAL)

    def _cleanup(self, saved_settings: dict[str, Any], state: "_RunState") -> str | None:
        errors = []
        try:
            self.api.put("/admin/settings", saved_settings)
            self.api.post("/admin/reset", {"prefix": PREFIX})
        except ApiError as err:
            errors.append(str(err))
        if self.zones is not None:
            for zone in sorted(state.zones):
                try:
                    self.zones.delete_zone(zone)
                except Exception as err:
                    errors.append(str(err))
        return "; ".join(errors) or None


@dataclass
class _RunState:
    names: dict[str, str]
    mark: float
    zones: set[str] = field(default_factory=set)


_PLACEHOLDER = re.compile(r"\$\{([a-z_][a-z0-9_]*)(?::(upper))?\}")


def _expand(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            key, upper = match.group(1), match.group(2)
            if key not in names:
                raise ScenarioError(f"unknown placeholder ${{{key}}}")
            return names[key].upper() if upper else names[key]

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [_expand(v, names) for v in value]
    if isinstance(value, dict):
        return {_expand(k, names): _expand(v, names) for k, v in value.items()}
    return value


def _subset_mismatch(expected: Any, actual: Any, path: str = "") -> str | None:
    """``None`` when every key/value of ``expected`` is present in ``actual``."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path or 'body'} is not an object"
        for key, value in expected.items():
            if key not in actual:
                return f"{path}{key} missing"
            mismatch = _subset_mismatch(value, actual[key], f"{path}{key}.")
            if mismatch:
                return mismatch
        return None
    if expected != actual:
        return f"{path.rstrip('.')} = {actual!r}, expected {expected!r}"
    return None
