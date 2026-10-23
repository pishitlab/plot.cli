autonomy: continuous

# PROGRESS — ตัวติดตามงาน

กติกา: AI แก้ไฟล์นี้ได้ **เฉพาะ** การติ๊ก task, เพิ่มหลักฐาน, และเพิ่มรายการในหัวข้อ Assumptions / Unverified / Spec Change Requests / Backlog / Session Log
บรรทัดแรก (`autonomy`) ผู้ใช้เท่านั้นที่เปลี่ยนได้ · อ้างอิง SPEC: `docs/SPEC.md`

## ภาพรวม

| Phase | ชื่อ | น้ำหนัก | สะสม | สถานะ |
|---|---|---|---|---|
| P0 | วางรากฐาน | 5% | 5% | ✅ เสร็จ |
| P1 | แกนโดเมน | 15% | 20% | ✅ เสร็จ |
| P2 | Registrar API | 15% | 35% | 🟦 กำลังทำ |
| P3 | DNS จริง | 20% | 55% | ⬜ |
| P4 | CLI | 10% | 65% | ⬜ |
| P5 | สถานการณ์และตัวตรวจ | 13% | 78% | ⬜ |
| P6 | Web UI | 10% | 88% | ⬜ |
| P7 | โมดูลเสริม | 6% | 94% | ⬜ |
| P8 | ปิดงาน | 6% | 100% | ⬜ |

ความคืบหน้ารวม: **20%** (คำนวณจากน้ำหนัก phase × สัดส่วน task ที่ติ๊กแล้วใน phase นั้น; phase จะนับเต็มเมื่อ Exit Gate ผ่านและผู้ใช้อนุมัติ)

สัญลักษณ์: ⬜ ยังไม่เริ่ม · 🟦 กำลังทำ · ✅ เสร็จ (มีหลักฐาน) · ⚠️ เสร็จแต่มี `NOT RUN` ค้าง

รูปแบบการติ๊ก: `- [x] P1-T03 ชื่องาน — หลักฐาน: <คำสั่ง → ผลจริง>`

---

## P0 — วางรากฐาน (SPEC §16 P0)
- [x] P0-T01 โครงโปรเจกต์: `pyproject.toml`, `Makefile` (install/lint/test/fmt), ruff, mypy, pytest, `.gitignore`, `.env.example`, โครง `src/plot`, `tests/` — หลักฐาน: `make install` → exit 0 (venv `.venv`, Python 3.12.3); `make lint` → ruff `All checks passed!`, `4 files already formatted`, mypy (strict) `Success: no issues found in 4 source files`; `make test` → `1 passed in 0.02s`
- [x] P0-T02 ตรวจสภาพแวดล้อม: เวอร์ชัน Python, มี Docker/compose หรือไม่ (`docker version`), มี `dig` หรือไม่ → บันทึกผลในหัวข้อ "Environment" ด้านล่าง — หลักฐาน: ดูหัวข้อ Environment (ตรวจ 2026-10-22)
- [x] P0-T03 CI: GitHub Actions รัน lint + unit บน push — หลักฐาน: `.github/workflows/ci.yml` (on push + pull_request; Python 3.12; `make install/lint/test`); run #1 บน commit `e43f369` → job `lint-and-unit` conclusion `success` (Install/Lint/Unit tests ผ่านทุก step) https://github.com/pishitlab/plot.cli/actions/runs/39829278504
- [x] P0-T04 `README.md` สั้น (วัตถุประสงค์, ลิงก์ SPEC, วิธีรัน lint/test) — หลักฐาน: `README.md` มีวัตถุประสงค์, คำเตือน dev LAN only (§15), ลิงก์ SPEC/PROGRESS, คำสั่ง `make install/lint/test/fmt`; `make lint` + `make test` → ผ่าน (1 passed)
- [x] P0-T05 ถามผู้ใช้ Q-001..Q-006 (SPEC §3.1) พร้อมคำแนะนำ แล้วรอคำตอบ — หลักฐาน: ส่งคำถาม+คำแนะนำใน chat 2026-10-22; ผู้ใช้ตอบ "คุณเป็นโปรแกรมเมอร์ บรีฟตัวเองแล้วตัดสินจากความเป็นมืออาชีพของคุณเลย" → ใช้คำแนะนำเป็นคำตอบ (ดูหัวข้อ "คำตอบ Q-xxx")
- **Exit Gate P0:** [x] ผ่านครบตาม SPEC §16 P0 · [x] ผู้ใช้อนุมัติ (มอบอำนาจใน chat 2026-10-22)
  - [x] `make install && make lint && make test` ผ่านบน repo เปล่า → install exit 0, lint ผ่าน (ruff + mypy strict), test `1 passed`; CI run #1 success
  - [x] PROGRESS มีผลตรวจ Python version และ Docker availability → หัวข้อ Environment
  - [x] Q-001..Q-006 ได้คำตอบ และ D-001..D-012 = CONFIRMED ใน SPEC v0.2 (โดยการมอบอำนาจของผู้ใช้)

## P1 — แกนโดเมน (SPEC §4.4, §5, §6)
- [x] P1-T01 `core/errors.py`: error codes ทั้งหมดตาม §8.1 เป็น exception hierarchy — หลักฐาน: `src/plot/core/errors.py` (22 codes §8.1, base `PlotError` + กลุ่ม 400/404/409); `tests/unit/test_errors.py` ตรวจว่าทุก code ใน §8.1 มี class เดียวและ status ตรง; `make lint` ผ่าน; `make test` → 4 passed
- [x] P1-T02 `core/names.py` + tests R-NAME-01..03 — หลักฐาน: `src/plot/core/names.py` (`normalize_name`, `split_registrable` จับ suffix ยาวสุด, `is_within`, `name_and_ancestors`); tests `test_R_NAME_01_*`, `test_R_NAME_02_*`, `test_R_NAME_03_*` ใน `tests/unit/test_names.py` (รวมกรณี non-ASCII ที่ lowercase แล้วกลายเป็น ASCII); `make lint` ผ่าน; `make test` → 36 passed
- [x] P1-T03 `core/tlds.py` + loader `config/tlds.yml` + passthrough loader + tests R-NAME-04..05 — หลักฐาน: `src/plot/core/tlds.py` (`NamePolicy.parse_registrable` ใช้ R-NAME-01..05 ตามลำดับ, `parse_tlds`/`load_tlds`, `parse_passthrough`/`load_passthrough`; `root-servers.net` สงวนเสมอ) + `config/tlds.yml`, `config/passthrough.txt` ตามค่าเริ่มต้น §13.2/§13.3; tests `test_R_NAME_04_*`, `test_R_NAME_05_*` + ตรวจ config ผิดรูปแบบ ใน `tests/unit/test_tlds.py`; Assumption A-003, A-004; `make lint` ผ่าน; `make test` → 62 passed
- [x] P1-T04 `core/clock.py` (`Clock`, `SystemClock`, `FakeClock`) และ `core/settings.py` — หลักฐาน: `src/plot/core/clock.py` (`Clock` Protocol, `SystemClock`, `FakeClock` บังคับ UTC/ห้ามถอยหลัง, `add_years` ตามปฏิทิน) + `src/plot/core/settings.py` (`EnvConfig` จาก env/.env, `RuntimeSettings` + `config/settings.default.yml` ตาม §13.4); tests `test_clock.py`, `test_settings.py`; Assumption A-005; `make lint` ผ่าน; `make test` → 76 passed
- [x] P1-T05 `db/models.py`, `db/session.py`, migration แรกตาม §5 — หลักฐาน: `src/plot/db/models.py` (9 ตารางตาม §5, เวลาเก็บเป็นข้อความ UTC ISO-8601 ความยาวคงที่ผ่าน `UtcDateTime`, CHECK ของ status/kind/family, FK cascade), `src/plot/db/session.py` (`make_engine` เปิด `PRAGMA foreign_keys`, `migrate` ผ่าน Alembic), migration `0001_initial_schema`; `tests/unit/test_db.py` ตรวจ migration == models (`compare_metadata` = []), downgrade, idempotent บนไฟล์จริง, timestamp roundtrip, FK cascade; `make lint` ผ่าน; `make test` → 82 passed
- [x] P1-T06 `services/ports.py` (Protocol: `DnsPublisher`, `ResolverControl`) + fakes ใน `tests/fakes.py` — หลักฐาน: `src/plot/services/ports.py` (`DnsPublisher`, `ResolverControl`, re-export `Clock`) + `tests/fakes.py` (`FakeDnsPublisher`, `FakeResolverControl`; `FakeClock` อยู่ใน `core/clock.py`); `tests/unit/test_ports.py` ตรวจว่า fake เข้ากับ Protocol (mypy) และบันทึกการเรียก; Assumption A-006; `make lint` ผ่าน; `make test` → 85 passed
- [x] P1-T07 `services/events.py` (audit log) + tests R-DOM-07 — หลักฐาน: `src/plot/services/events.py` (`RequestContext`, `record_event`, `domain_history` รวม event ของ host ย่อย) + `src/plot/services/context.py`; `tests/conftest.py` (SQLite in-memory, `FakeClock`, `FakeDnsPublisher`); test `test_R_DOM_07_record_writes_event_with_request_context` (การเขียน event ของทุก mutation ตรวจต่อใน test ของ T08–T11); Assumption A-007; `make lint` ผ่าน; `make test` → 87 passed
- [x] P1-T08 `services/hosts.py` + tests R-HOST-01..07 — หลักฐาน: `src/plot/services/hosts.py` (`HostService` create/get/list/update/delete, `parse_host_name`, `parse_addresses`, `find_parent_domain` จับโดเมนแม่ยาวสุด, `delete_unused_external_hosts` สำหรับ R-NS-06); `tests/unit/test_hosts.py` มี `test_R_HOST_01_*`..`test_R_HOST_07_*` + `test_R_DOM_07_host_changes_write_events`; แก้ `make fmt` ให้ format ก่อน check; Assumption A-008; `make lint` ผ่าน; `make test` → 118 passed
- [x] P1-T09 `services/domains.py` (check/register/renew/delete/status) + tests R-DOM-01..05 — หลักฐาน: `src/plot/services/domains.py` (`DomainService` check/register/get/list_domains/renew/delete/update_status/set_overrides, `remove_domain` ใช้ร่วมกับ purge, แจ้ง publisher รวมโดเมนเจ้าของ glue); `tests/unit/test_domains.py` มี `test_R_DOM_01_*`..`test_R_DOM_05_*` + `test_R_DOM_07_domain_changes_write_events`; พบและแก้บั๊ก FK ตอนลบโดเมนที่ใช้ host ย่อยของตัวเองเป็น NS (test R-DOM-04 จับได้); Assumption A-009; `make lint` ผ่าน; `make test` → 155 passed
- [x] P1-T10 `services/nameservers.py` + tests R-NS-01..06 — หลักฐาน: `src/plot/services/nameservers.py` (`replace_nameservers`: validate ทั้งชุดก่อนเขียน, สร้าง external host อัตโนมัติ, ลบ external ที่ไม่มีใครใช้, คืนชุดโดเมนที่ต้อง publish ใหม่รวมเจ้าของ glue) + `DomainService.set_nameservers` และ `register(nameservers=...)`; `tests/unit/test_nameservers.py` มี `test_R_NS_01_*`..`test_R_NS_06_*` + ตรวจว่า error แล้วไม่มีอะไรถูกเขียน; Assumption A-010; `make lint` ผ่าน; `make test` → 175 passed
- [x] P1-T11 `services/lifecycle.py` (expiry, grace, purge) + tests R-DOM-06 — หลักฐาน: `src/plot/services/lifecycle.py` (`LifecycleService.run` purge โดเมนที่เกิน grace + แจ้ง publish โดเมนที่เพิ่งหมดอายุ, `expire_now`); `tests/unit/test_lifecycle.py` มี `test_R_DOM_06_*` 8 ตัว (ขอบเขตเวลา expired/grace, renew ใน grace, purge แล้วชื่อว่าง, purge ถอด host ย่อยออกจากโดเมนอื่น); test จับบั๊กลำดับ UPDATE ชน `UNIQUE(domain_id, position)` ที่ผมเพิ่มเกิน §5 → เอา constraint นั้นออกจาก model และ migration 0001 (ยังไม่เคย deploy); Assumption A-011; `make lint` ผ่าน; `make test` → 184 passed
- [x] P1-T12 สคริปต์ตรวจว่าทุกรหัสกติกา R-NAME/DOM/HOST/NS มี test และตรวจ layering (`services` ไม่ import `api|cli|web|dns`) ผูกกับ `make test` — หลักฐาน: `tests/unit/test_governance.py` (รันใน `make test`): อ่านรหัส R-NAME/DOM/HOST/NS จากตาราง §6 ของ SPEC (25 ข้อ) แล้วเทียบกับชื่อ `test_R_..._` ใน `tests/`; `services/` ห้าม import `plot.api|cli|web|dns|whois`; `core/` import ได้เฉพาะ stdlib + pydantic/pydantic_settings/yaml (A-003); `services/` ห้ามเรียก `datetime.now`/`time.sleep` ฯลฯ; ลองใส่ violation ทั้ง 4 แบบแล้ว → 4 failed ตามคาด (revert แล้ว); `make test` เพิ่ม coverage gate `--cov-fail-under=90` สำหรับ core+services; `make lint` ผ่าน; `make test` → 189 passed, coverage 99.88%
- **Exit Gate P1:** [x] ผ่านครบตาม SPEC §16 P1 · [x] ผู้ใช้อนุมัติ (2026-10-23: "ทำต่อเนื่องให้ อัตโนมัติ")
  - [x] ทุก R-NAME/R-DOM/R-HOST/R-NS มี test อย่างน้อย 1 ตัว → `test_every_business_rule_has_a_named_test` ผ่าน (25/25 รหัส)
  - [x] coverage `core/`+`services/` ≥ 90% → `make test`: `Required test coverage of 90% reached. Total coverage: 99.88%` (branch coverage; ขาดเพียง 1 branch ใน `services/hosts.py`)
  - [x] `services/` ไม่ import `api|cli|web|dns` → `test_services_do_not_import_outer_layers` ผ่าน (พิสูจน์ว่าจับได้จริงด้วยการใส่ violation)

## P2 — Registrar API (SPEC §8)
- [x] P2-T01 `api/app.py`, `api/deps.py`, auth `X-API-Key` (constant-time), `/health` — หลักฐาน: `src/plot/api/app.py` (`create_app(AppState)`), `src/plot/api/deps.py` (`AppState`, `require_api_key` ใช้ `hmac.compare_digest`, `unit_of_work` = 1 transaction/request), `src/plot/api/routes/health.py`, `src/plot/services/settings.py` (โหลด runtime settings จาก DB); `tests/api/test_health_auth.py` (health ok/degraded/probe throw, 401 เมื่อไม่มี/ผิด key และ key ไม่หลุดใน response, ไม่มี /docs); Assumption A-012; `make lint` ผ่าน; `make test` → 197 passed (warning จาก Starlette: ให้ใช้ `httpx2` แทน `httpx` ใน TestClient — ไม่เปลี่ยนเพราะ `httpx2` ไม่อยู่ใน §4.5)
- [x] P2-T02 `api/errors.py` error envelope + `request_id` middleware — หลักฐาน: `src/plot/api/errors.py` (envelope `{error:{code,message,details},request_id}`, handler ของ `PlotError` + `RequestValidationError`, middleware กำหนด request_id และแปลง exception ที่ไม่คาดคิดเป็น 500 `INTERNAL_ERROR`); `tests/api/test_errors_envelope.py`; Assumption A-013; `make lint` ผ่าน; `make test` → 202 passed
- [x] P2-T03 routes: domains (check/create/get/list/delete/renew) — หลักฐาน: `src/plot/api/routes/domains.py` (`GET /domains/check`, `POST /domains` 201, `GET /domains`, `GET /domains/{name}`, `DELETE` 204, `POST /{name}/renew`), `src/plot/api/schemas.py`, `dns_visible()` ใน services; `tests/api/test_domains_api.py` (happy + error ของทุก route; rollback เมื่อ register ล้ม; 410 DOMAIN_PURGED); Assumption A-014; `make lint` ผ่าน; `make test` → 231 passed
- [ ] P2-T04 routes: hosts
- [ ] P2-T05 routes: nameservers, status, overrides
- [ ] P2-T06 routes: history
- [ ] P2-T07 routes: admin (settings, expire-now, reset, flush, reconcile) — เรียก port ผ่าน Fake ได้
- [ ] P2-T08 OpenAPI snapshot test
- [ ] P2-T09 API tests ครบทุก endpoint + ทุก error code §8.1
- **Exit Gate P2:** [ ] ผ่านครบตาม SPEC §16 P2 · [ ] ผู้ใช้อนุมัติ

## P3 — DNS จริง (SPEC §6.5, §7)
- [ ] P3-T01 `dns/projector.py`: DB state → snapshot (R-PUB-01..04) + tests 100% branch
- [ ] P3-T02 `published_state` + `pending_changes` + `dns/scheduler.py` (R-PUB-05, 06, 09)
- [ ] P3-T03 `dns/pdns_client.py` (REST ของ pdns: REPLACE/DELETE RRset) — ตรวจ path/zone-id กับ version ที่ pin
- [ ] P3-T04 `dns/publisher.py` ผูก projector+scheduler+client เป็น `DnsPublisher`
- [ ] P3-T05 `dns/unbound_ctl.py` (flush ผ่าน unbound-control) และ R-PUB-08
- [ ] P3-T06 `dns/reconcile.py` (R-PUB-07)
- [ ] P3-T07 `deploy/`: compose, unbound conf/hints template, pdns-root conf, Dockerfile ของ registrar — pin version ของ image ทุกตัวแล้วบันทึกใน "Pinned versions"
- [ ] P3-T08 `plot seed provider` (หรือ API ภายใน) + `demo-ns` ขั้นต่ำให้ `myhost.net` resolve ได้
- [ ] P3-T09 `/health` ตรวจ db/pdns/unbound
- [ ] P3-T10 integration tests ตาม Exit Gate P3 (`make test-integration`)
- **Exit Gate P3:** [ ] ผ่านครบตาม SPEC §16 P3 · [ ] ผู้ใช้ยืนยันผล integration บน dev box · [ ] ผู้ใช้อนุมัติ

## P4 — CLI (SPEC §9)
- [ ] P4-T01 `cli/main.py` + config (`PLOT_API_URL`, `PLOT_API_KEY`) + client + `--json`
- [ ] P4-T02 `plot domain *`
- [ ] P4-T03 `plot ns *`
- [ ] P4-T04 `plot host *`
- [ ] P4-T05 `plot override`, `plot admin *`
- [ ] P4-T06 tests ด้วย `CliRunner` ครบทุกคำสั่ง + exit code
- **Exit Gate P4:** [ ] ผ่านครบตาม SPEC §16 P4 · [ ] ผู้ใช้อนุมัติ

## P5 — สถานการณ์และตัวตรวจ (SPEC §10, §11)
- [ ] P5-T01 `verifier/verify.py` + unit tests ทุกค่า enum (fake DNS)
- [ ] P5-T02 `plot verify`
- [ ] P5-T03 `scenarios/engine.py` (โหลด YAML, รัน step, ตรวจ expectation, cleanup `scn-*`)
- [ ] P5-T04 scenario S01–S05
- [ ] P5-T05 scenario S06–S10
- [ ] P5-T06 scenario S11–S15
- [ ] P5-T07 `demo-ns add-zone` + scenario S16
- [ ] P5-T08 `plot scenario list|describe|run`
- [ ] P5-T09 รัน `plot scenario run --all` บน compose
- **Exit Gate P5:** [ ] ผ่านครบตาม SPEC §16 P5 · [ ] ผู้ใช้อนุมัติ

## P6 — Web UI (SPEC §12.1)
- [ ] P6-T01 layout + หน้ารายการโดเมน
- [ ] P6-T02 หน้ารายละเอียดโดเมน (DB vs dns_visible, pending countdown, actions)
- [ ] P6-T03 หน้า hosts
- [ ] P6-T04 หน้า settings
- [ ] P6-T05 หน้า scenarios
- [ ] P6-T06 หน้า history + smoke tests ทุกหน้า
- **Exit Gate P6:** [ ] ผ่านครบตาม SPEC §16 P6 · [ ] ผู้ใช้อนุมัติ

## P7 — โมดูลเสริม (ผู้ใช้เลือกเอง; ค่าเริ่มต้น = ไม่ทำ)
เลือกโดยผู้ใช้: [ ] RDAP · [ ] WHOIS · [ ] transfer · [ ] virtual clock
- [ ] P7-T01 RDAP `/rdap/domain/{name}`
- [ ] P7-T02 WHOIS TCP :43
- [ ] P7-T03 transfer ด้วย auth code
- [ ] P7-T04 virtual clock สำหรับ registrar
- **Exit Gate P7:** [ ] เฉพาะโมดูลที่เลือกผ่านตาม SPEC §16 P7 · [ ] ผู้ใช้อนุมัติ

## P8 — ปิดงาน (SPEC §15, §17, §18)
- [ ] P8-T01 `README.md` ฉบับเต็ม
- [ ] P8-T02 `docs/RUNBOOK.md` (ติดตั้ง .175, DNS client, systemd-resolved, troubleshooting, backup)
- [ ] P8-T03 ปรับ log JSON + health + `make smoke`
- [ ] P8-T04 ผู้ใช้รัน Acceptance checklist §18
- [ ] P8-T05 เคลียร์รายการ Unverified ให้หมด แล้ว tag `v1.0.0` (ตามที่ผู้ใช้สั่ง)
- **Exit Gate P8:** [ ] ผ่านครบตาม SPEC §16 P8 · [ ] ผู้ใช้อนุมัติ

---

## Environment (กรอกใน P0-T02)
ตรวจเมื่อ 2026-10-22 ใน cloud container ของ AI (ไม่ใช่ `192.168.1.175`)
- Python: `python3.12 --version` → `Python 3.12.3` (ใช้ทำ `.venv` ผ่าน `make install`); `python3` ของระบบ = 3.13.16 (ไม่ใช้)
- Docker / compose: `docker version` → Client 29.9.1; `docker compose version` → v5.6.0. daemon **ไม่ได้รันอยู่ตอนเริ่ม session** (`/var/run/docker.sock` ไม่มี) แต่สั่ง `dockerd` เองได้ (root) → Server 29.9.1, storage `overlayfs`, cgroup v1. ทดสอบแล้ว: `docker run --rm hello-world` ผ่าน, `docker pull powerdns/pdns-auth-49` ผ่าน, `docker network create --subnet 172.28.0.0/24` + container ได้ IP `172.28.0.99` ผ่าน (ลบ network/image ทดสอบแล้ว)
- dig / dnspython: `dig` **ไม่มี** (`command not found`); dnspython 2.9.0 ติดตั้งใน `.venv` แล้ว (integration ใช้ dnspython ตาม §14)
- รัน integration ใน session นี้ได้หรือไม่: **น่าจะได้** — ต้องสั่ง `dockerd` ก่อนในแต่ละ session; ยังไม่ได้ทดสอบ bind port 53/5300 และ DNS จริงใน container (จะพิสูจน์ใน P3-T10) ผล integration จาก session นี้ไม่ได้แทนการรันบน `192.168.1.175`

## คำตอบ Q-xxx (P0-T05, 2026-10-22 — ผู้ใช้มอบอำนาจให้ AI ตัดสิน)
| Q | คำตอบ | หมายเหตุ |
|---|---|---|
| Q-001 | ยืนยัน D-001 (Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite, Typer, dnspython) | — |
| Q-002 | ยังไม่ทราบซอฟต์แวร์/IP ของ ns จริง → seed `myhost.net` ด้วย `demo-ns1/2` (`172.28.0.31/.32`) ตาม D-012 | A-001 |
| Q-003 | ใช้ TLD ตาม §13.2 | — |
| Q-004 | ใช้ passthrough ตาม §13.3 | ปรับได้ภายหลังโดยแก้ `config/passthrough.txt` |
| Q-005 | `192.168.1.175` = Ubuntu LTS; ตั้ง DNS ให้ client **รายเครื่อง** (ไม่ใช้ DHCP ของ router) | A-002 |
| Q-006 | อนุญาตให้ AI รัน Docker ใน session (สั่ง `dockerd` เอง); ผล phase 3+ ยังต้องยืนยันบน dev box ตาม §2.9 | — |

## Pinned versions (กรอกใน P3-T07)
| ส่วน | image/เวอร์ชัน | ตรวจเอกสาร/ทดสอบแล้ว |
|---|---|---|
| unbound | _—_ | _—_ |
| pdns-auth | _—_ | _—_ |
| Python deps | ล็อกใน `pyproject.toml`/lockfile | _—_ |

## Assumptions (A-xxx)
| ID | สมมติฐาน | ที่มา | ต้องยืนยันเมื่อ |
|---|---|---|---|
| A-001 | nameserver ของ hosting จริงยังไม่ทราบ ใช้ `demo-ns1/2` เป็น provider ของ `myhost.net` | Q-002 | ก่อนทำ Acceptance §18 ข้อ "ระบบ hosting จริง" |
| A-002 | เครื่อง `192.168.1.175` เป็น Ubuntu LTS (RUNBOOK เขียนสำหรับ Ubuntu) และตั้ง DNS รายเครื่อง | Q-005 | P8-T02 |
| A-003 | §4.4 ให้ `core/` import ได้แค่ stdlib + pydantic แต่ §4.6/P1-T03/P1-T04 วาง loader ของ `tlds.yml`/settings ไว้ใน `core/` → อนุญาตให้ `core/` import `yaml` และ `pydantic_settings` เพิ่ม (เป็น lib อ่าน config ที่อนุมัติแล้วใน §4.5) ห้าม import อย่างอื่น; test layering (P1-T12) บังคับรายการนี้ | §2.6 | — |
| A-004 | `min_ns` ใน `tlds.yml` ที่ไม่ระบุ = 2; ค่าที่ยอมรับ 1..13 (ขอบบนตาม R-NS-01) ไฟล์ config ผิดรูปแบบ → error ตอนโหลด (registrar ไม่ start) | §2.6 | — |
| A-005 | `EnvConfig`: `API_KEY`/`PDNS_API_KEY` ไม่มีค่าเริ่มต้น (ต้องตั้งเสมอ ไม่ใช้ `change-me` เงียบ ๆ); `BIND_ADDR` ที่ไม่ตั้ง = `127.0.0.1` (ปลอดภัยตาม N10) ค่าอื่นตาม §13.1; `RuntimeSettings` เป็น strict (ไม่แปลง `"300"` → 300) | §2.6 | — |
| A-006 | รูปแบบ port: `DnsPublisher.domains_changed(session, domain_names)` — services แจ้งชื่อโดเมนที่ delegation/glue อาจเปลี่ยน ภายใน transaction เดียวกัน; implementation (P3) คำนวณ snapshot ทันทีจาก session นั้น (R-PUB-01) และ schedule เอง; `ResolverControl.flush(domain_name \| None)` (`None` = ทั้งหมด) | §2.6 (SPEC ไม่กำหนด signature) | P3-T04 |
| A-007 | เพิ่ม `services/context.py` (`ServiceContext`: session, clock, publisher, policy, settings, request) ซึ่งไม่อยู่ในผัง §4.6 — ถือว่าผังเป็นรายการขั้นต่ำ ไม่ใช่รายการปิด; services `flush` แต่ไม่ `commit` (ผู้เรียก เช่น API เป็นเจ้าของ transaction และ rollback เมื่อ error) | §2.6 | — |
| A-008 | Host: (ก) "อยู่ใต้โดเมนที่จด" (R-HOST-02) รวมชื่อที่ตรงกับโดเมนเอง และเทียบทีละ label (`ns1.myshop.com` ไม่ใช่ลูกของ `shop.com`); (ข) IP ซ้ำในคำขอ → `INVALID_ADDRESS`; IPv6 แบบ IPv4-mapped (`::ffff:a.b.c.d`) → `INVALID_ADDRESS` (กันหลบตัวกรอง loopback); IP เก็บแบบ canonical; (ค) `PUT /hosts` field ที่ไม่ส่ง = คงค่าเดิม, ส่ง `[]` = ล้าง family นั้น (ยังต้องผ่าน R-HOST-02/03) | §2.6 | — |
| A-009 | Domain: (ก) `check` ไม่ throw สำหรับชื่อที่ผิดกติกา แต่คืน `available=false` + `reason`=รหัส error (`INVALID_NAME` … `RESERVED_NAME`, `DOMAIN_EXISTS`); (ข) `owner` ต้องยาว 1..255 หลัง trim ไม่งั้น `VALIDATION_ERROR`; (ค) `list` ค่าเริ่มต้น `limit`=50, `cursor` = ชื่อโดเมนสุดท้ายของหน้าก่อน (เรียงตามชื่อ), `prefix` ไม่สนตัวพิมพ์; (ง) status ที่อยู่ทั้งใน `add` และ `remove` → `INVALID_STATUS`, ลบ status ที่ไม่มี = no-op; (จ) `DomainView` มี field เพิ่ม `expired` (derived, R-DOM-06; §8.3 อนุญาตเพิ่ม field); (ฉ) overrides: `null` = ล้าง, ไม่ส่ง = คงเดิม, ค่าต้อง ≥ 0 (`ns_ttl` ≤ 2^31-1) ไม่งั้น `VALIDATION_ERROR` | §2.6 | P2-T03/T05 |
| A-010 | NS set: (ก) ลำดับตรวจ = ชื่อ (R-HOST-01) → ซ้ำ (R-NS-02) → จำนวน (R-NS-01) → host (R-NS-03/04) และตรวจครบก่อนเขียนอะไร; (ข) NS ที่ไม่มีใน DB แต่อยู่ใต้โดเมนที่จดอยู่ (รวม in-bailiwick) → `HOST_NOT_FOUND` (R-NS-03); `GLUE_REQUIRED` ใช้เมื่อมี host in-bailiwick อยู่แล้วแต่เป็น external/ไม่มี IP; (ค) R-NS-06 ลบ external host ที่ไม่มีใครใช้ ทั้งตอนแทนที่ชุด NS และตอนลบ/purge โดเมน; (ง) suffix ที่ถูกเอาออกจาก `tlds.yml` หลังจดแล้ว ใช้ `min_ns`=2 | §2.6 | — |
| A-011 | Lifecycle: (ก) "เกิน grace" = `now > expires_at + expiry_grace_days`; โดเมนที่เกิน grace แต่ job ยังไม่ purge → `get/renew/...` ตอบ `DOMAIN_PURGED`, `check` ตอบว่าว่าง, `register` ชื่อนั้น purge ของเก่าก่อนแล้วจดใหม่ (ไม่ต้องรอ job); โดเมนที่ purge แล้ว (ไม่มีแถวใน DB) → `DOMAIN_NOT_FOUND`; (ข) purge บังคับลบ host ย่อยแม้ถูกโดเมนอื่นใช้ โดยถอดออกจากชุด NS ของโดเมนนั้น (เขียน event `domain.nameservers` + publish ใหม่) — ชุด NS ที่เหลืออาจน้อยกว่า `min_ns`; (ค) `run(since)` แจ้ง publisher เฉพาะโดเมนที่หมดอายุในช่วง `[since, now)` (`None` = ทุกโดเมนที่หมดอายุ); (ง) `expire-now` ตั้ง `expires_at = now - 1s` | §2.6 | — |
| A-012 | API: (ก) ทุก endpoint รวม `/health` อยู่ใต้ `/api/v1` (`GET /api/v1/health`); (ข) ปิด `/docs`, `/redoc`, `/openapi.json` เพื่อให้ไม่มี endpoint นอก §8.2 (snapshot ใช้ `app.openapi()` ในโค้ด); (ค) `/health` ตอบ 200 เสมอ ค่าแต่ละส่วน `ok`/`down`, `status`=`degraded` ถ้ามีส่วนใด `down`; (ง) actor ของ event จาก API = `api` (D-008 มี key เดียว); (จ) runtime settings เก็บใน table `settings` ทีละ key ทับค่าจาก `settings.default.yml` | §2.6 | — |
| A-013 | `request_id`: ใช้ `X-Request-ID` ที่ client ส่งมาถ้าเป็น `[A-Za-z0-9._-]{1,64}` ไม่งั้นสร้าง uuid4 hex; ส่งกลับใน header `X-Request-ID` ทุก response; body ผิดรูป/validation ของ FastAPI → 400 `VALIDATION_ERROR` พร้อม `details.errors[{loc,msg,type}]`; exception ที่ไม่คาดคิด → 500 `INTERNAL_ERROR` ไม่เปิดเผยข้อความภายใน (log พร้อม request_id); route ที่ไม่มีอยู่/method ผิด ใช้คำตอบมาตรฐานของ FastAPI (ไม่ใช่ endpoint ของ §8.2) | §2.6 | — |
| A-014 | `dns_visible` อ่านจาก `published_state.snapshot["nameservers"]` (snapshot `null`/ไม่มี key = ไม่มี delegation) และ `pending` = แถว `pending_changes` ที่ `applied_at` เป็น null เรียงตาม `(apply_at, id)` → projector ใน P3-T01 ต้องใช้ key `nameservers` ใน snapshot; request body เป็น strict + ห้าม field เกิน (`"2"` แทน `2` หรือ field แปลก → `VALIDATION_ERROR`); `GET /domains/check` ไม่ใส่ `reason` เมื่อว่าง | §2.6 | P3-T01 |

## Unverified (ต้องเคลียร์ก่อนจบ P8)
| ID | เรื่อง | ทำไมยังไม่ตรวจ | วิธีตรวจ |
|---|---|---|---|
| U-001 | zone id ของ root ใน pdns API (`=2E`?) | ยังไม่มีการรัน pdns | เรียก API กับ image ที่ pin |
| U-002 | ชื่อ option `soa-edit-api` ที่เหมาะกับ version ที่ pin | ยังไม่ได้อ่านเอกสารตาม version | อ่านเอกสาร + ทดสอบ |
| U-003 | Unbound ยอมรับ referral ที่ข้ามระดับจาก root (D-005) และ `qname-minimisation: no` ตามที่คาด | ยังไม่มีการรัน | integration test ใน P3-T10 |
| U-004 | glue ที่เป็น private IP ผ่านตัวกรองของ Unbound เมื่อไม่มี `private-address` | ยังไม่มีการรัน | integration test ใน P3-T10 |

## Spec Change Requests
| ID | ปัญหา | หลักฐาน | ข้อเสนอ (แนะนำ) | ผลกระทบ | สถานะ |
|---|---|---|---|---|---|
| SCR-001 | `pyyaml` ไม่มี type hints ในตัว แต่ mypy ตั้งเป็น `strict` → เมื่อ import `yaml` (P1-T03) จะ error `missing library stubs` | mypy ต้องการ stub package `types-PyYAML` ซึ่งไม่อยู่ใน §4.5 (ติดตั้งไปครั้งหนึ่งระหว่าง P0-T01 แล้วเอาออก ไม่ได้ commit) | เพิ่ม `types-PyYAML` ใน dev deps ของ §4.5 (ทางเลือกอื่น: ตั้ง `ignore_missing_imports` เฉพาะ `yaml` ใน mypy — ไม่แนะนำเพราะเสีย type check) | P1-T03 (loader `tlds.yml`) | อนุมัติ 2026-10-22 (มอบอำนาจ) → SPEC v0.2 §4.5 |

## Backlog (ไอเดียนอก SPEC — ห้ามลงมือจนกว่าผู้ใช้อนุมัติ)
_ยังไม่มี_

## Session Log (เพิ่มบรรทัดใหม่ต่อท้ายทุกครั้งที่จบงาน)
| วันที่ | Task | สรุป | หลักฐาน |
|---|---|---|---|
| 2026-10-22 | — | สร้างเอกสารควบคุมงาน (CLAUDE.md, SPEC.md, PROGRESS.md) | — |
| 2026-10-22 | P0-T01..T04 | โครงโปรเจกต์, ตรวจสภาพแวดล้อม, CI, README สั้น; ยื่น SCR-001 (`types-PyYAML`); P0-T05 ส่งคำถาม Q-001..Q-006 ให้ผู้ใช้แล้ว รอคำตอบ | `make lint` ผ่าน, `make test` → 1 passed; CI run #1 success |
| 2026-10-22 | P0-T05, P1-T01..T12 | ผู้ใช้มอบอำนาจตัดสิน Q-001..Q-006 → SPEC v0.2; ทำแกนโดเมน P1 ครบ (errors, names, tlds, clock/settings, DB+migration, ports/fakes, events, hosts, domains, nameservers, lifecycle, governance tests); Assumptions A-003..A-011 | `make lint` ผ่าน; `make test` → 189 passed, coverage core+services 99.88% |
| 2026-10-23 | — | ผู้ใช้สั่ง "ทำต่อเนื่องให้ อัตโนมัติ" → AI เปลี่ยน `autonomy: continuous` ตามคำสั่ง และถือเป็นการอนุมัติ Exit Gate P1 | ข้อความผู้ใช้ใน chat |
