autonomy: stepwise

# PROGRESS — ตัวติดตามงาน

กติกา: AI แก้ไฟล์นี้ได้ **เฉพาะ** การติ๊ก task, เพิ่มหลักฐาน, และเพิ่มรายการในหัวข้อ Assumptions / Unverified / Spec Change Requests / Backlog / Session Log
บรรทัดแรก (`autonomy`) ผู้ใช้เท่านั้นที่เปลี่ยนได้ · อ้างอิง SPEC: `docs/SPEC.md`

## ภาพรวม

| Phase | ชื่อ | น้ำหนัก | สะสม | สถานะ |
|---|---|---|---|---|
| P0 | วางรากฐาน | 5% | 5% | ✅ เสร็จ |
| P1 | แกนโดเมน | 15% | 20% | 🟦 กำลังทำ |
| P2 | Registrar API | 15% | 35% | ⬜ |
| P3 | DNS จริง | 20% | 55% | ⬜ |
| P4 | CLI | 10% | 65% | ⬜ |
| P5 | สถานการณ์และตัวตรวจ | 13% | 78% | ⬜ |
| P6 | Web UI | 10% | 88% | ⬜ |
| P7 | โมดูลเสริม | 6% | 94% | ⬜ |
| P8 | ปิดงาน | 6% | 100% | ⬜ |

ความคืบหน้ารวม: **5%** (คำนวณจากน้ำหนัก phase × สัดส่วน task ที่ติ๊กแล้วใน phase นั้น; phase จะนับเต็มเมื่อ Exit Gate ผ่านและผู้ใช้อนุมัติ)

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
- [ ] P1-T05 `db/models.py`, `db/session.py`, migration แรกตาม §5
- [ ] P1-T06 `services/ports.py` (Protocol: `DnsPublisher`, `ResolverControl`) + fakes ใน `tests/fakes.py`
- [ ] P1-T07 `services/events.py` (audit log) + tests R-DOM-07
- [ ] P1-T08 `services/hosts.py` + tests R-HOST-01..07
- [ ] P1-T09 `services/domains.py` (check/register/renew/delete/status) + tests R-DOM-01..05
- [ ] P1-T10 `services/nameservers.py` + tests R-NS-01..06
- [ ] P1-T11 `services/lifecycle.py` (expiry, grace, purge) + tests R-DOM-06
- [ ] P1-T12 สคริปต์ตรวจว่าทุกรหัสกติกา R-NAME/DOM/HOST/NS มี test และตรวจ layering (`services` ไม่ import `api|cli|web|dns`) ผูกกับ `make test`
- **Exit Gate P1:** [ ] ผ่านครบตาม SPEC §16 P1 · [ ] ผู้ใช้อนุมัติ

## P2 — Registrar API (SPEC §8)
- [ ] P2-T01 `api/app.py`, `api/deps.py`, auth `X-API-Key` (constant-time), `/health`
- [ ] P2-T02 `api/errors.py` error envelope + `request_id` middleware
- [ ] P2-T03 routes: domains (check/create/get/list/delete/renew)
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
