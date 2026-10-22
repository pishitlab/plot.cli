autonomy: stepwise

# PROGRESS — ตัวติดตามงาน

กติกา: AI แก้ไฟล์นี้ได้ **เฉพาะ** การติ๊ก task, เพิ่มหลักฐาน, และเพิ่มรายการในหัวข้อ Assumptions / Unverified / Spec Change Requests / Backlog / Session Log
บรรทัดแรก (`autonomy`) ผู้ใช้เท่านั้นที่เปลี่ยนได้ · อ้างอิง SPEC: `docs/SPEC.md`

## ภาพรวม

| Phase | ชื่อ | น้ำหนัก | สะสม | สถานะ |
|---|---|---|---|---|
| P0 | วางรากฐาน | 5% | 5% | ⬜ ยังไม่เริ่ม |
| P1 | แกนโดเมน | 15% | 20% | ⬜ |
| P2 | Registrar API | 15% | 35% | ⬜ |
| P3 | DNS จริง | 20% | 55% | ⬜ |
| P4 | CLI | 10% | 65% | ⬜ |
| P5 | สถานการณ์และตัวตรวจ | 13% | 78% | ⬜ |
| P6 | Web UI | 10% | 88% | ⬜ |
| P7 | โมดูลเสริม | 6% | 94% | ⬜ |
| P8 | ปิดงาน | 6% | 100% | ⬜ |

ความคืบหน้ารวม: **0%** (คำนวณจากน้ำหนัก phase × สัดส่วน task ที่ติ๊กแล้วใน phase นั้น; phase จะนับเต็มเมื่อ Exit Gate ผ่านและผู้ใช้อนุมัติ)

สัญลักษณ์: ⬜ ยังไม่เริ่ม · 🟦 กำลังทำ · ✅ เสร็จ (มีหลักฐาน) · ⚠️ เสร็จแต่มี `NOT RUN` ค้าง

รูปแบบการติ๊ก: `- [x] P1-T03 ชื่องาน — หลักฐาน: <คำสั่ง → ผลจริง>`

---

## P0 — วางรากฐาน (SPEC §16 P0)
- [ ] P0-T01 โครงโปรเจกต์: `pyproject.toml`, `Makefile` (install/lint/test/fmt), ruff, mypy, pytest, `.gitignore`, `.env.example`, โครง `src/plot`, `tests/`
- [ ] P0-T02 ตรวจสภาพแวดล้อม: เวอร์ชัน Python, มี Docker/compose หรือไม่ (`docker version`), มี `dig` หรือไม่ → บันทึกผลในหัวข้อ "Environment" ด้านล่าง
- [ ] P0-T03 CI: GitHub Actions รัน lint + unit บน push
- [ ] P0-T04 `README.md` สั้น (วัตถุประสงค์, ลิงก์ SPEC, วิธีรัน lint/test)
- [ ] P0-T05 ถามผู้ใช้ Q-001..Q-006 (SPEC §3.1) พร้อมคำแนะนำ แล้วรอคำตอบ
- **Exit Gate P0:** [ ] ผ่านครบตาม SPEC §16 P0 · [ ] ผู้ใช้อนุมัติ

## P1 — แกนโดเมน (SPEC §4.4, §5, §6)
- [ ] P1-T01 `core/errors.py`: error codes ทั้งหมดตาม §8.1 เป็น exception hierarchy
- [ ] P1-T02 `core/names.py` + tests R-NAME-01..03
- [ ] P1-T03 `core/tlds.py` + loader `config/tlds.yml` + passthrough loader + tests R-NAME-04..05
- [ ] P1-T04 `core/clock.py` (`Clock`, `SystemClock`, `FakeClock`) และ `core/settings.py`
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
- Python: _ยังไม่ตรวจ_
- Docker / compose: _ยังไม่ตรวจ_
- dig / dnspython: _ยังไม่ตรวจ_
- รัน integration ใน session นี้ได้หรือไม่: _ยังไม่ทราบ_

## Pinned versions (กรอกใน P3-T07)
| ส่วน | image/เวอร์ชัน | ตรวจเอกสาร/ทดสอบแล้ว |
|---|---|---|
| unbound | _—_ | _—_ |
| pdns-auth | _—_ | _—_ |
| Python deps | ล็อกใน `pyproject.toml`/lockfile | _—_ |

## Assumptions (A-xxx)
_ยังไม่มี_

## Unverified (ต้องเคลียร์ก่อนจบ P8)
| ID | เรื่อง | ทำไมยังไม่ตรวจ | วิธีตรวจ |
|---|---|---|---|
| U-001 | zone id ของ root ใน pdns API (`=2E`?) | ยังไม่มีการรัน pdns | เรียก API กับ image ที่ pin |
| U-002 | ชื่อ option `soa-edit-api` ที่เหมาะกับ version ที่ pin | ยังไม่ได้อ่านเอกสารตาม version | อ่านเอกสาร + ทดสอบ |
| U-003 | Unbound ยอมรับ referral ที่ข้ามระดับจาก root (D-005) และ `qname-minimisation: no` ตามที่คาด | ยังไม่มีการรัน | integration test ใน P3-T10 |
| U-004 | glue ที่เป็น private IP ผ่านตัวกรองของ Unbound เมื่อไม่มี `private-address` | ยังไม่มีการรัน | integration test ใน P3-T10 |

## Spec Change Requests
_ยังไม่มี_

## Backlog (ไอเดียนอก SPEC — ห้ามลงมือจนกว่าผู้ใช้อนุมัติ)
_ยังไม่มี_

## Session Log (เพิ่มบรรทัดใหม่ต่อท้ายทุกครั้งที่จบงาน)
| วันที่ | Task | สรุป | หลักฐาน |
|---|---|---|---|
| 2026-10-22 | — | สร้างเอกสารควบคุมงาน (CLAUDE.md, SPEC.md, PROGRESS.md) | — |
