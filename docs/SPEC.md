# Domain Sandbox — SPEC (v0.1, สถานะ: DRAFT รอผู้ใช้ยืนยัน §3)

เอกสารนี้คือแหล่งความจริงเดียวของโปรเจกต์ AI ต้องทำงานตามเอกสารนี้ ห้ามตีความเพิ่มเอง
ถ้าเอกสารไม่ครอบคลุมหรือคลุมเครือ ให้ใช้ขั้นตอน §2.6 (Ambiguity Protocol)

---

## 1. วัตถุประสงค์และขอบเขต

### 1.1 ปัญหา
ระบบ hosting ที่กำลังพัฒนามีฟีเจอร์ "เพิ่มโดเมน → ให้ลูกค้าตั้ง nameserver → ระบบตรวจว่า NS ชี้มาหาเราแล้ว → ยืนยันความเป็นเจ้าของ"
การทดสอบกับของจริงต้องใช้ IP จริงและโดเมนจริง ซ้ำหลายครั้งไม่ได้

### 1.2 สิ่งที่ต้องส่งมอบ
ระบบที่รันบนเครื่อง `192.168.1.175` ให้เครื่อง dev ตั้ง DNS มาที่เครื่องนี้ แล้วได้ "อินเทอร์เน็ตจำลอง" ประกอบด้วย

1. **DNS resolver** ที่เดินจาก root จำลอง (Unbound)
2. **Registry** = zone `.` จำลอง เก็บ delegation (NS) และ glue ของทุกโดเมนที่จด (PowerDNS Authoritative)
3. **Registrar** = REST API + CLI (+ Web UI ในภายหลัง) สำหรับจดโดเมน, ตั้ง/เปลี่ยน nameserver, จด host (child nameserver) พร้อม IP
4. **ตัวควบคุมสถานการณ์**: propagation delay, TTL, hold, expire, lame delegation, reset
5. **Reference verifier**: เครื่องมือตรวจ NS แบบอ้างอิง ใช้พิสูจน์ว่า sandbox ทำงานถูก และเป็นตัวอย่างให้ระบบ hosting

### 1.3 Non-goals (ห้ามทำ)
- ไม่ติดต่อ registrar/registry จริง ไม่จดโดเมนจริง
- ไม่ทำ DNSSEC (ปิด validation ทั้งระบบ)
- ไม่ทำ billing, ชำระเงิน, อีเมลยืนยัน, multi-tenant จริงจัง
- ไม่ implement EPP protocol (ใช้ REST เท่านั้น)
- ไม่ทำ IDN conversion (รับ `xn--` ตามที่ให้มา)
- ไม่ re-classify host (external → subordinate) ย้อนหลัง
- ไม่ทำ HA/cluster เครื่องเดียวพอ

---

## 2. กติกาควบคุม AI (Governance)

### 2.1 ลำดับความสำคัญ
`docs/SPEC.md` > `docs/PROGRESS.md` > chat ถ้าขัดกัน ให้หยุดและรายงานความขัดแย้ง

### 2.2 วงจรทำงานต่อ 1 task
1. อ่าน PROGRESS → เลือก task ถัดไปที่ยังไม่ติ๊ก (ห้ามข้าม)
2. อ่านหัวข้อ SPEC ที่ task อ้างถึง
3. **เขียน test ก่อน** สำหรับกติกา R-xxx ที่เกี่ยวข้อง (ดู §14)
4. เขียนโค้ดให้ test ผ่านด้วยการเปลี่ยนน้อยที่สุด
5. รัน gate ของ task (`make lint`, `make test`, และอื่นตามที่ระบุ)
6. อัปเดต PROGRESS (ติ๊ก + หลักฐาน + ส่วนที่ไม่ได้ตรวจสอบ)
7. commit ข้อความขึ้นต้นด้วย task ID
8. ถ้าเป็น task สุดท้ายของ phase → ตรวจ Exit Gate (§16) แล้วรายงาน (ภาคผนวก A)

### 2.3 ห้ามเด็ดขาด
| # | ข้อห้าม |
|---|---|
| N1 | ทำฟีเจอร์นอก SPEC หรือ "ปรับปรุงเพิ่มให้" โดยไม่ได้รับอนุมัติ |
| N2 | เปลี่ยน Decision (§3), API contract (§8), CLI contract (§9) หรือกติกา R-xxx (§6) โดยไม่ผ่าน Spec Change (§2.5) |
| N3 | เพิ่ม/เปลี่ยน dependency นอกรายการอนุมัติ (§4.5) |
| N4 | ข้าม, ปิด, comment-out, หรือผ่อน test เพื่อให้ผ่าน |
| N5 | อ้างผลที่ไม่ได้รันจริง (ใช้คำว่า `NOT RUN` แทน) |
| N6 | เดาชื่อ option/endpoint ของ Unbound, PowerDNS, Docker ให้ตรวจกับ version ที่ pin หรือเอกสารทางการ ถ้าตรวจไม่ได้ให้ลง "Unverified" |
| N7 | ใส่ secret, token จริง, หรือ IP/โดเมนจริงของผู้ใช้ลง repo (ใช้ `.env` ที่ ignore และ `.env.example`) |
| N8 | เรียก DNS/registrar/API ภายนอกที่ไม่ใช่ upstream resolver ที่ตั้งใน config |
| N9 | force push, แก้ history, สร้าง PR (เว้นแต่ผู้ใช้สั่ง) |
| N10 | เปิด port 53/8080/5300 ให้ออกอินเทอร์เน็ต หรือ bind `0.0.0.0` โดยไม่ผ่านตัวแปร `BIND_ADDR` |
| N11 | แก้ไฟล์ `docs/SPEC.md` เอง ยกเว้นผ่าน Spec Change ที่ผู้ใช้อนุมัติแล้ว |

### 2.4 Definition of Done (ต่อ task)
- [ ] test ครอบคลุมกติกา R-xxx ที่เกี่ยวข้อง และชื่อ test มีรหัสกติกา
- [ ] `make lint` (ruff + mypy) ผ่าน
- [ ] `make test` ผ่าน (แปะจำนวน passed/failed จริง)
- [ ] ไม่มี `TODO`/`print` debug ค้าง ไม่มี dead code
- [ ] อัปเดต PROGRESS พร้อมหลักฐาน
- [ ] commit แล้ว (ข้อความ `Pn-Txx: ...`)

### 2.5 Spec Change Request
ถ้า AI เห็นว่า SPEC ผิด/ขาด/ทำไม่ได้จริง ให้
1. หยุด task ที่ได้รับผลกระทบ
2. เขียนใน PROGRESS หัวข้อ "Spec Change Requests": ปัญหา, หลักฐาน, ข้อเสนอ (พร้อมแนะนำ 1 ทางเลือก), ผลกระทบต่อ task/phase อื่น
3. ถามผู้ใช้ รอคำตอบ
4. เมื่ออนุมัติ: แก้ SPEC พร้อมบรรทัดใน Changelog (§19) ใน commit เดียวกับโค้ดที่เกี่ยวข้อง

### 2.6 Ambiguity Protocol
ถ้า SPEC คลุมเครือแต่ไม่ block: เลือกทางที่ **ง่ายและสอดคล้องกับกติกาข้างเคียงที่สุด**, ทำต่อ, และบันทึกใน PROGRESS หัวข้อ "Assumptions" (ID `A-xxx`)
ถ้า block (เช่น กระทบ API contract): ถามผู้ใช้พร้อมคำแนะนำ 1 ทาง ไม่ถามคำถามกว้าง ๆ

### 2.7 Autonomy mode
กำหนดใน PROGRESS บรรทัดแรก: `autonomy: stepwise` (ค่าเริ่มต้น) หรือ `continuous` ผู้ใช้เท่านั้นที่เปลี่ยนได้
- `stepwise`: จบ phase แล้วหยุดรออนุมัติ
- `continuous`: ไป phase ถัดไปได้เองเมื่อ Exit Gate ผ่านครบทุกข้อ แต่ **ต้องหยุดทันที** เมื่อเจอ Spec Change, test ล้มที่แก้ไม่ได้ใน 2 รอบ, หรือเจอสิ่งที่ตรวจสอบไม่ได้และกระทบ phase ถัดไป

### 2.8 Git
- ทำงานบน branch ที่ผู้ใช้กำหนดเท่านั้น (ไม่สร้าง/พุชไป branch อื่น)
- commit เล็ก หนึ่ง task = หนึ่งหรือไม่กี่ commit ขึ้นต้นด้วย `Pn-Txx:`
- push หลังจบแต่ละ task หรืออย่างน้อยจบแต่ละ phase

### 2.9 ข้อจำกัดของสภาพแวดล้อม
AI อาจรันใน container ที่ **ไม่มี Docker** ให้ตรวจใน P0-T02 แล้วบันทึกผล
- ถ้าไม่มี Docker: ทำ phase 1–2 ได้เต็ม, phase 3+ ให้เขียนโค้ด/config/integration test ให้ครบ แต่ติ๊ก integration ว่า `NOT RUN (needs docker)` และให้ผู้ใช้รัน `make test-integration` บน dev box แล้วส่งผลกลับมา **phase จะถือว่าจบสมบูรณ์เมื่อผู้ใช้ยืนยันผล integration เท่านั้น**

---

## 3. Decision Log

สถานะ: `ASSUMED` = AI/ผู้ร่างตั้งค่าเริ่มต้นไว้ รอผู้ใช้ยืนยัน, `CONFIRMED` = ผู้ใช้ยืนยันแล้ว AI เปลี่ยนสถานะเองไม่ได้

| ID | หัวข้อ | การตัดสินใจ | สถานะ |
|---|---|---|---|
| D-001 | ภาษา/เฟรมเวิร์ก | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite, Typer (CLI), dnspython | ASSUMED |
| D-002 | Registry | PowerDNS Authoritative (backend `gsqlite3`) ถือ zone `.` เป็น registry ทั้งก้อน | ASSUMED |
| D-003 | Resolver | Unbound เดินจาก root จำลองเท่านั้น (iterator, ไม่มี DNSSEC) | ASSUMED |
| D-004 | โหมด resolve | **isolated + passthrough list**: ชื่อที่ไม่ได้จด → NXDOMAIN ยกเว้นโดเมนใน `config/passthrough.txt` (forward ไป upstream จริง) และโดเมนใน list นั้นจดใน sandbox ไม่ได้ | ASSUMED |
| D-005 | Delegation | root จำลอง delegate โดเมนระดับที่จดได้ตรง ๆ (ไม่มี TLD server คั่น) | ASSUMED |
| D-006 | Host | host ภายนอก (ไม่มีโดเมนแม่ในระบบ) สร้างอัตโนมัติเมื่อถูกใช้เป็น NS และห้ามมี IP; host ย่อย (subordinate) ต้องสร้างเองพร้อม IP | ASSUMED |
| D-007 | Delay | DB/WHOIS/RDAP เปลี่ยนทันที แต่ DNS เปลี่ยนหลัง `propagation_delay` | ASSUMED |
| D-008 | Auth | API key เดียวผ่าน header `X-API-Key` (ค่าใน `.env`) ไม่มี user/role | ASSUMED |
| D-009 | Deploy | Docker Compose บน `192.168.1.175` | ASSUMED |
| D-010 | Subnet ภายใน | `172.28.0.0/24` (ปรับได้ใน `.env`) | ASSUMED |
| D-011 | IPv6 | ปิด (`do-ip6: no`) host รับ AAAA ได้ในข้อมูลแต่ resolver ไม่ใช้ IPv6 | ASSUMED |
| D-012 | Nameserver ของ hosting จริง | ยังไม่ทราบซอฟต์แวร์ (BIND/PowerDNS/CoreDNS) → sandbox มี `demo-ns` ของตัวเองไว้ทดสอบแทน | ASSUMED |

### 3.1 คำถามที่ผู้ใช้ต้องตอบก่อนจบ P0 (Q-xxx)
- Q-001 ยืนยัน D-001 (stack) หรือระบุภาษาอื่น
- Q-002 ระบบ hosting ใช้ nameserver ซอฟต์แวร์อะไร และ IP ของ ns1/ns2 (ถ้ามีแล้ว) — ใช้กำหนดค่า seed
- Q-003 รายการ TLD ที่ต้องการ (ค่าเริ่มต้นใน §13.2) และมี TLD แปลก ๆ ที่ต้องการเพิ่มไหม
- Q-004 รายการโดเมนจริงที่ dev ต้องเข้าถึงผ่าน DNS นี้ (passthrough เริ่มต้นใน §13.3)
- Q-005 ระบบปฏิบัติการของ `192.168.1.175` และตั้ง DNS ให้ client อย่างไร (DHCP ที่ router หรือรายเครื่อง)
- Q-006 รัน Docker ใน session ที่ AI ทำงานได้หรือไม่ (ดู §2.9)

---

## 4. สถาปัตยกรรม

### 4.1 ภาพรวม

```
 เครื่อง dev / hosting app ──DNS:53──▶  192.168.1.175 (Docker Compose)
                                       ┌────────────────────────────────────────────┐
                                       │ unbound        172.28.0.2   :53 (published)│
                                       │   │ root-hints → 172.28.0.10               │
                                       │   │ forward-zone ต่อโดเมนใน passthrough    │
                                       │   ▼                                        │
                                       │ pdns-root      172.28.0.10  :53            │
                                       │   zone "."  (registry)      :5300 published│
                                       │   ▲ REST API (internal :8081)              │
                                       │ registrar      172.28.0.20  :8080 published│
                                       │   └─ SQLite /data/registrar.db             │
                                       │ demo-ns1       172.28.0.31  :53   (optional)│
                                       │ demo-ns2       172.28.0.32  :53   (optional)│
                                       └────────────────────────────────────────────┘
 nameserver ของ hosting จริง (ns1/ns2) อยู่ IP อื่นใน LAN เช่น 192.168.1.176/.177
```

### 4.2 หน้าที่ของแต่ละส่วน
| ส่วน | หน้าที่ | ห้ามทำ |
|---|---|---|
| `registrar` | เจ้าของข้อมูลทั้งหมด (DB) + กติกาธุรกิจ + สั่ง publish ไป pdns + สั่ง flush Unbound | ห้ามตอบ DNS เอง |
| `pdns-root` | ตอบ DNS ของ zone `.` ตามที่ registrar เขียน | ห้ามมีข้อมูลที่ไม่ได้มาจาก registrar |
| `unbound` | resolver ให้ client | ห้ามมี local-data ของโดเมนที่จด |
| `demo-ns*` | nameserver จำลองของ "provider" เพื่อทดสอบ end-to-end | ไม่ใช่ส่วนของ registry |

### 4.3 Network และ port
| Port | บริการ | เปิดออกโฮสต์ | หมายเหตุ |
|---|---|---|---|
| 53/udp+tcp | unbound | ใช่ (`BIND_ADDR`) | resolver ที่ client ใช้ |
| 5300/udp+tcp | pdns-root | ใช่ (`BIND_ADDR`) | "registry view" ไว้ถาม delegation ตรง (dev เท่านั้น) |
| 8080/tcp | registrar API/UI | ใช่ (`BIND_ADDR`) | |
| 43/tcp | WHOIS | ใช่ (ถ้าเปิดฟีเจอร์ P7) | |
| 8081/tcp | pdns API | **ไม่** | internal เท่านั้น |
| 8953/tcp | unbound-control | **ไม่** | internal เท่านั้น |

ข้อควรระวังบน Ubuntu: `systemd-resolved` จองพอร์ต 53 ที่ `127.0.0.53` ต้องตั้ง `DNSStubListener=no` (เขียนใน RUNBOOK §17)

### 4.4 Layering (บังคับ)
```
core  ←  services  ←  api / cli / web / whois
             ↑
             └── ports (Protocol): DnsPublisher, ResolverControl, Clock
                        ↑
                      dns/  (implementations: pdns_client, unbound_ctl)
```
- `core/` ไม่ import อะไรนอกจาก stdlib และ pydantic
- `services/` ไม่ import `api`, `cli`, `web`, `dns` (ใช้ผ่าน Protocol ที่ฉีดเข้ามา)
- ทุกการเข้าถึงเวลาใช้ `Clock` ห้ามเรียก `datetime.now()`/`time.sleep()` ใน services
- test ของ services/api ใช้ `FakeDnsPublisher`, `FakeResolverControl`, `FakeClock`

### 4.5 Dependencies ที่อนุมัติ
runtime: `fastapi`, `uvicorn`, `sqlalchemy>=2`, `alembic`, `pydantic>=2`, `pydantic-settings`, `typer`, `httpx`, `dnspython`, `pyyaml`, `jinja2` (P6)
dev: `pytest`, `pytest-cov`, `ruff`, `mypy`, `freezegun` (ห้ามใช้ถ้า FakeClock พอ)
อื่น ๆ ต้องขออนุมัติ

### 4.6 โครงสร้าง repo
```
CLAUDE.md
README.md
Makefile
pyproject.toml
.env.example
config/
  tlds.yml  passthrough.txt  settings.default.yml
deploy/
  docker-compose.yml
  unbound/unbound.conf.tmpl
  unbound/root.hints.tmpl
  pdns-root/pdns.conf
  registrar/Dockerfile
  demo-ns/pdns.conf
docs/
  SPEC.md  PROGRESS.md  RUNBOOK.md (P8)
src/plot/
  core/        names.py  tlds.py  errors.py  clock.py  settings.py
  db/          models.py  session.py  migrations/
  services/    domains.py  hosts.py  nameservers.py  lifecycle.py  events.py  ports.py
  dns/         projector.py  pdns_client.py  publisher.py  scheduler.py  unbound_ctl.py  reconcile.py
  api/         app.py  deps.py  errors.py  schemas.py  routes/
  cli/         main.py  commands/
  scenarios/   engine.py  catalog/*.yml
  verifier/    verify.py
  web/         templates/  static/        (P6)
  whois/       server.py  rdap.py         (P7)
tests/
  unit/  api/  integration/  scenarios/
```

---

## 5. โมเดลข้อมูล (SQLite)

เวลาทั้งหมดเก็บเป็น UTC ISO-8601 ชื่อโดเมน/host เก็บเป็น lowercase ไม่มีจุดท้าย

| ตาราง | คอลัมน์สำคัญ |
|---|---|
| `domains` | `id`, `name` UNIQUE, `suffix`, `label`, `owner`, `auth_code`, `created_at`, `expires_at`, `updated_at`, `ns_ttl_override` NULL, `delay_override` NULL |
| `domain_statuses` | `domain_id`, `status` (`clientHold` `serverHold` `pendingDelete`) UNIQUE(domain_id,status) |
| `hosts` | `id`, `name` UNIQUE, `kind` (`subordinate` `external`), `parent_domain_id` NULL, `created_at` |
| `host_addrs` | `host_id`, `family` (4/6), `address` UNIQUE(host_id,address) |
| `domain_ns` | `domain_id`, `position`, `host_id` UNIQUE(domain_id,host_id) |
| `events` | `id`, `ts`, `request_id`, `actor` (api-key label/cli), `action`, `domain_name` NULL, `host_name` NULL, `before` JSON, `after` JSON |
| `pending_changes` | `id`, `domain_name`, `snapshot` JSON, `scheduled_at`, `apply_at`, `applied_at` NULL |
| `published_state` | `domain_name` PK, `snapshot` JSON, `published_at` |
| `settings` | `key` PK, `value` JSON |

`snapshot` = ชุด RRset ที่ควรปรากฏใน zone `.` สำหรับโดเมนนั้น (delegation + glue) หรือ `null` ถ้าต้องไม่มี

---

## 6. กติกาธุรกิจ (ทุกข้อต้องมี test ชื่อมีรหัส)

### 6.1 ชื่อ
| ID | กติกา | error |
|---|---|---|
| R-NAME-01 | normalize: trim, lowercase, ตัดจุดท้าย 1 ตัว; ว่าง → ผิด | `INVALID_NAME` |
| R-NAME-02 | ทุก label: `[a-z0-9-]`, ยาว 1–63, ไม่ขึ้นต้น/ลงท้ายด้วย `-`; ความยาวรวม ≤ 253; ไม่รับ `_` | `INVALID_NAME` |
| R-NAME-03 | โดเมนที่จดได้ = **1 label + suffix ที่รองรับ** (จับ suffix ยาวสุด) เช่น `shop.co.th` ได้, `www.shop.com` ไม่ได้ | `NOT_REGISTRABLE` |
| R-NAME-04 | suffix ต้องอยู่ใน `config/tlds.yml` | `TLD_NOT_SUPPORTED` |
| R-NAME-05 | ชื่อที่ตรง/อยู่ใต้โดเมนใน `passthrough.txt` หรือ `root-servers.net` จดไม่ได้ | `RESERVED_NAME` |

### 6.2 โดเมน
| ID | กติกา | error |
|---|---|---|
| R-DOM-01 | ชื่อซ้ำจดไม่ได้ (ไม่ว่าเจ้าของใคร) | `DOMAIN_EXISTS` 409 |
| R-DOM-02 | `years` 1–10 (ค่าเริ่มต้น `default_years`), `expires_at = created_at + years` (ตามปฏิทิน) | `INVALID_PERIOD` |
| R-DOM-03 | ต่ออายุแล้วอายุคงเหลือรวมต้องไม่เกิน 10 ปี | `RENEW_LIMIT` |
| R-DOM-04 | ลบโดเมนได้เมื่อ host ย่อยของมันไม่ถูกใช้เป็น NS ของโดเมนอื่น; ลบแล้ว host ย่อยถูกลบด้วย; ชื่อว่างทันที | `HOST_IN_USE` 409 |
| R-DOM-05 | status ที่ตั้งได้: `clientHold`, `serverHold`, `pendingDelete` (ผ่าน admin) | `INVALID_STATUS` |
| R-DOM-06 | `expired` = `now > expires_at` (derived); ต่ออายุคืนสถานะได้ถ้าไม่เกิน `expiry_grace_days` (ค่าเริ่มต้น 30); เกินแล้วถูก purge (ชื่อว่าง) โดย lifecycle job | `DOMAIN_PURGED` |
| R-DOM-07 | ทุกการเปลี่ยนแปลงเขียน `events` | — |

### 6.3 Host
| ID | กติกา | error |
|---|---|---|
| R-HOST-01 | ชื่อ host ต้องผ่าน R-NAME-01/02 และมี ≥ 2 label | `INVALID_NAME` |
| R-HOST-02 | **subordinate** = ชื่ออยู่ใต้โดเมนที่จดในระบบ (จับโดเมนแม่ที่ยาวสุด) ต้องมี IP อย่างน้อย 1 | `HOST_ADDR_REQUIRED` |
| R-HOST-03 | **external** = ไม่มีโดเมนแม่ในระบบ ห้ามมี IP | `HOST_ADDR_FORBIDDEN` |
| R-HOST-04 | IP ต้องถูกรูปแบบ v4/v6; ห้าม `0.0.0.0`, loopback, multicast, link-local; **อนุญาต private (RFC1918)** | `INVALID_ADDRESS` |
| R-HOST-05 | แก้ IP ของ host ได้ (มีผลต่อ glue) | — |
| R-HOST-06 | ลบ host ที่ถูกใช้เป็น NS ของโดเมนใดไม่ได้ | `HOST_IN_USE` 409 |
| R-HOST-07 | host ซ้ำชื่อไม่ได้ | `HOST_EXISTS` 409 |

### 6.4 Nameserver set
| ID | กติกา | error |
|---|---|---|
| R-NS-01 | `PUT nameservers` แทนที่ทั้งชุด; ขนาดชุด = 0 หรือ `min_ns`(ต่อ TLD, ค่าเริ่มต้น 2)…13 | `INVALID_NS_COUNT` |
| R-NS-02 | ชื่อ NS ซ้ำกันในชุดเดียว (หลัง normalize) ไม่ได้ | `DUPLICATE_NS` |
| R-NS-03 | NS ที่เป็น host ย่อยต้องมีอยู่แล้ว; NS ภายนอกสร้างอัตโนมัติ (D-006) | `HOST_NOT_FOUND` |
| R-NS-04 | NS ที่อยู่ใต้โดเมนเดียวกัน (in-bailiwick) ต้องเป็น host ย่อยที่มี IP (ต้องมี glue) | `GLUE_REQUIRED` |
| R-NS-05 | ชุดว่าง = โดเมนยังจดอยู่แต่ไม่มี delegation | — |
| R-NS-06 | ถ้า NS ถูกแทนที่แล้ว host ภายนอกที่ไม่มีใครใช้ถูกลบอัตโนมัติ | — |

### 6.5 Publishing
| ID | กติกา |
|---|---|
| R-PUB-01 | DNS ที่มองเห็นได้ = ฟังก์ชันของ snapshot ที่คำนวณ ณ เวลาสั่งเปลี่ยน (ไม่ใช่ DB ตอน apply) และ **idempotent** |
| R-PUB-02 | delegation (NS ของโดเมน) ถูกเผยแพร่เมื่อ: ไม่มี `clientHold`/`serverHold`/`pendingDelete`, ไม่ `expired`, ชุด NS ไม่ว่าง |
| R-PUB-03 | glue (A/AAAA ของ host ย่อย) เผยแพร่เมื่อ delegation ของโดเมนแม่ถูกเผยแพร่ **และ** host ถูกใช้เป็น NS ของโดเมนใดโดเมนหนึ่ง |
| R-PUB-04 | TTL ของ NS/glue = `ns_ttl_override` ของโดเมน ถ้าไม่มีใช้ `settings.ns_ttl` (ค่าเริ่มต้น 300) |
| R-PUB-05 | `apply_at = now + (delay_override ?? settings.propagation_delay)` (ค่าเริ่มต้น 0) |
| R-PUB-06 | `pending_changes` ถูก apply ตามลำดับ `(apply_at, id)`; snapshot ที่ใหม่กว่าของโดเมนเดียวกันทับของเก่า |
| R-PUB-07 | เมื่อ registrar เริ่มทำงาน → reconcile: เทียบ `published_state` กับ zone ใน pdns แก้ drift; แล้ว re-schedule `pending_changes` ที่ยังไม่ apply |
| R-PUB-08 | หลัง apply สำเร็จต้อง flush cache ของ Unbound สำหรับโดเมนนั้น (ถ้า `flush_on_apply=true`, ค่าเริ่มต้น true) |
| R-PUB-09 | ถ้า pdns ล้ม: การเปลี่ยนแปลงคง pending และ retry (backoff 1,2,4,…,30 วิ); API ยังตอบสำเร็จ; `/health` รายงาน degraded |

---

## 7. DNS publishing และข้อกำหนดของ resolver

### 7.1 Zone `.` ใน pdns
- `SOA`: serial ใช้ค่าที่ pdns จัดการ (`soa-edit-api=INCEPTION-INCREMENT` หรือเทียบเท่า — **ต้องตรวจกับ version ที่ pin**), `minimum` = 5 วินาที (negative caching สั้น)
- `NS .` = `a.root-servers.net.` และ `A a.root-servers.net.` = `${PDNS_ROOT_IP}` (ไว้ให้ `root.hints` อ้าง)
- ต่อโดเมนที่จด (ถ้าผ่าน R-PUB-02): `NS <domain>` ตามชุด NS + glue A/AAAA ของ host ย่อยที่ผ่าน R-PUB-03
- การเขียนทำผ่าน pdns HTTP API แบบ `REPLACE`/`DELETE` ของ RRset (zone id ของ root ใน API ตรวจกับ version ที่ pin — คาดว่าเป็น `=2E`)

### 7.2 Unbound — ข้อกำหนดที่ต้องมีใน `unbound.conf.tmpl`
(ทุกข้อต้องตรวจกับ version ที่ pin และพิสูจน์ด้วย integration test)
- `module-config: "iterator"` (ไม่มี validator) และไม่มี trust-anchor
- `root-hints` ชี้ `a.root-servers.net` → `${PDNS_ROOT_IP}` (port 53 ภายใน network)
- `qname-minimisation: no`
- `harden-glue: no`, `harden-referral-path: no`, `harden-dnssec-stripped: no`
- `do-not-query-localhost: no`; **ห้ามมี `private-address`** (ไม่งั้น glue 192.168.x.x ถูกกรอง)
- `do-ip6: no` (D-011)
- `access-control`: refuse ทั้งหมด ยกเว้น `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` = allow
- `cache-max-negative-ttl: 10`; `cache-min-ttl: 0`; `cache-max-ttl` จาก env (ค่าเริ่มต้น 3600)
- `infra-host-ttl` สั้น (เช่น 10) เพื่อให้ lame server ฟื้นเร็วใน test
- `remote-control`: เปิดบน interface ภายใน, `control-use-cert: no`
- `forward-zone` หนึ่งบล็อกต่อโดเมนใน `passthrough.txt` → `UPSTREAM_DNS` (ค่าเริ่มต้น `1.1.1.1`)
- log ระดับ `verbosity: 1`

### 7.3 Registry view
`dig @<BIND_ADDR> -p 5300 <domain> NS +norec` ต้องคืน **referral** (AUTHORITY section มี NS, ADDITIONAL มี glue) ใช้เป็นจุดอ้างอิง "parent delegation" ของ verifier

---

## 8. API contract (REST, prefix `/api/v1`)

Header: `X-API-Key: <key>` ทุก endpoint ยกเว้น `/health` · Body/Response เป็น JSON · เวลาเป็น ISO-8601 UTC

### 8.1 Error envelope
```json
{ "error": { "code": "DOMAIN_EXISTS", "message": "domain already registered", "details": {} }, "request_id": "..." }
```
| HTTP | ใช้เมื่อ | code ที่เป็นไปได้ |
|---|---|---|
| 400 | ข้อมูลไม่ถูกกติกา | `INVALID_NAME` `NOT_REGISTRABLE` `TLD_NOT_SUPPORTED` `RESERVED_NAME` `INVALID_PERIOD` `INVALID_STATUS` `INVALID_ADDRESS` `INVALID_NS_COUNT` `DUPLICATE_NS` `HOST_ADDR_REQUIRED` `HOST_ADDR_FORBIDDEN` `GLUE_REQUIRED` `VALIDATION_ERROR` |
| 401 | key ผิด/ไม่มี | `UNAUTHORIZED` |
| 404 | ไม่พบ | `DOMAIN_NOT_FOUND` `HOST_NOT_FOUND` |
| 409 | ชน/ถูกใช้อยู่ | `DOMAIN_EXISTS` `HOST_EXISTS` `HOST_IN_USE` `RENEW_LIMIT` |
| 410 | ถูก purge | `DOMAIN_PURGED` |
| 500 | ไม่คาดคิด | `INTERNAL_ERROR` |

### 8.2 Endpoints
| Method | Path | Body → Response (สรุป) |
|---|---|---|
| GET | `/health` | `{status: ok/degraded, db, pdns, unbound}` (ไม่ต้อง key) |
| GET | `/domains/check?name=` | `{name, available, reason?}` |
| POST | `/domains` | `{name, years?, owner, nameservers?[]}` → 201 Domain |
| GET | `/domains` | query: `prefix`, `owner`, `limit`(≤200), `cursor` → `{items[], next_cursor}` |
| GET | `/domains/{name}` | Domain (มี `dns_visible` ด้วย ดู 8.3) |
| DELETE | `/domains/{name}` | 204 |
| POST | `/domains/{name}/renew` | `{years}` → Domain |
| PUT | `/domains/{name}/nameservers` | `{nameservers: ["ns1.x.net", ...]}` → Domain |
| PUT | `/domains/{name}/status` | `{add?: [...], remove?: [...]}` → Domain |
| PUT | `/domains/{name}/overrides` | `{propagation_delay?: int\|null, ns_ttl?: int\|null}` → Domain |
| GET | `/domains/{name}/history` | `{items: [Event]}` |
| POST | `/hosts` | `{name, ipv4?: [], ipv6?: []}` → 201 Host |
| GET | `/hosts/{name}` · `/hosts` | Host / list |
| PUT | `/hosts/{name}` | `{ipv4?, ipv6?}` → Host |
| DELETE | `/hosts/{name}` | 204 |
| GET / PUT | `/admin/settings` | `{propagation_delay, ns_ttl, default_years, expiry_grace_days, flush_on_apply}` |
| POST | `/admin/domains/{name}/expire-now` | ตั้ง `expires_at` ไปอดีตเพื่อทดสอบ (ไม่ใช้ใน production flow) |
| POST | `/admin/reset` | `{prefix?: string, all?: bool}` ลบโดเมน/host (ยกเว้น seed) + ล้าง DNS + flush resolver |
| POST | `/admin/resolver/flush` | `{domain?}` |
| POST | `/admin/publish/reconcile` | บังคับ reconcile |

### 8.3 Shapes
```
Domain  = { name, owner, status: [..], created_at, expires_at, nameservers: [..],
            overrides: {propagation_delay, ns_ttl},
            dns_visible: { published_at, nameservers: [..], pending: [{apply_at}] } }
Host    = { name, kind, parent_domain, ipv4: [..], ipv6: [..], used_by: [domain..] }
Event   = { ts, action, actor, before, after, request_id }
```
`dns_visible` คือสิ่งที่ DNS "เห็น" (จาก `published_state` + `pending_changes`) ซึ่งอาจต่างจาก `nameservers` เมื่อมี delay

กติกา: การเพิ่ม field ใหม่ใน response ทำได้, การลบ/เปลี่ยนชื่อ/เปลี่ยนความหมายต้อง Spec Change · มี OpenAPI snapshot test (P2-T08) กันการเปลี่ยนเงียบ ๆ

---

## 9. CLI contract (`plot`, Typer)

ตัวแปร: `PLOT_API_URL` (ค่าเริ่มต้น `http://localhost:8080`), `PLOT_API_KEY` · ทุกคำสั่งรองรับ `--json` · exit code: 0 สำเร็จ, 1 error จาก API (พิมพ์ `code: message`), 2 ใช้คำสั่งผิด

```
plot domain check <name>
plot domain register <name> [--years N] [--owner O] [--ns NS ...]
plot domain info <name>
plot domain list [--prefix P] [--owner O]
plot domain renew <name> --years N
plot domain delete <name>
plot domain hold <name> | release <name>
plot domain expire-now <name>
plot ns set <domain> <ns1> <ns2> ... | plot ns clear <domain>
plot host create <name> [--ipv4 IP ...] [--ipv6 IP ...]
plot host update <name> [--ipv4 ...] [--ipv6 ...]
plot host delete <name> | info <name> | list
plot override <domain> [--delay S|none] [--ttl S|none]
plot admin settings [--delay S] [--ttl S]
plot admin reset [--prefix P | --all]
plot admin flush [<domain>]
plot seed provider [--domain myhost.net] [--ns1-ip IP] [--ns2-ip IP]
plot scenario list | run <id|--all> | describe <id>
plot verify <domain> --expect <ns1> <ns2> ...
plot demo-ns add-zone <domain> [--a IP]   (P5)
```

---

## 10. Scenario catalog

Scenario = ไฟล์ YAML (steps ที่เรียก API + ค่าที่คาดหวังจาก DNS) รันด้วย `plot scenario run` ทุกข้อใช้โดเมนสุ่มขึ้นต้น `scn-` เพื่อ reset ได้

| ID | ชื่อ | สิ่งที่ต้องเห็น |
|---|---|---|
| S01 | happy path (NS ภายนอก) | จด `scn-a.com`, ตั้ง NS = `ns1/ns2.myhost.net` → verifier = `VERIFIED` |
| S02 | child NS + glue | จด `scn-b.com`, สร้าง `ns1.scn-b.com`+IP, ตั้ง NS → registry view มี glue |
| S03 | ยังไม่ตั้ง NS | จดแล้วไม่ตั้ง → NS query = NXDOMAIN, verifier = `NOT_DELEGATED` |
| S04 | ชี้ไปผู้ให้บริการอื่น | NS = `ns1.other.net` → verifier = `MISMATCH` |
| S05 | partial | NS = {ns1.myhost.net, ns1.other.net} → verifier = `PARTIAL` |
| S06 | propagation delay | delay=20 → ทันทีหลังตั้ง NS ยัง `NOT_DELEGATED`, หลัง ~20s = `VERIFIED` |
| S07 | เปลี่ยนออกหลัง verified | ตั้งถูก → verified → เปลี่ยน NS → re-verify = `MISMATCH` |
| S08 | lame delegation | NS ชี้ host ที่ IP ไม่มี server ตอบ → verifier = `LAME` |
| S09 | hold | ตั้ง `serverHold` → delegation หาย → `NOT_DELEGATED`; release → กลับมา |
| S10 | expire | `expire-now` → delegation หาย; renew ภายใน grace → กลับมา |
| S11 | โดเมนซ้ำ | จดซ้ำ → `DOMAIN_EXISTS` |
| S12 | ไม่เคยจด | NS query = NXDOMAIN, verifier = `NXDOMAIN` |
| S13 | TTL/cache | ตั้ง ttl=300, resolve แล้วเปลี่ยน NS → resolver เห็นของเก่าจนกว่า flush (ถ้า `flush_on_apply=false`) |
| S14 | normalize | ใส่ `NS1.MyHost.NET.` และ `Shop.COM.` ได้ผลเหมือนตัวพิมพ์เล็กไม่มีจุดท้าย |
| S15 | host lifecycle | ลบ host ที่ถูกใช้ → `HOST_IN_USE`; ลบโดเมนที่มี host ย่อยถูกใช้โดยโดเมนอื่น → `HOST_IN_USE` |
| S16 | end-to-end site | `demo-ns add-zone` + A record → `dig @resolver www.<domain>` ได้ IP (P5) |

---

## 11. Reference verifier

หน้าที่: ตอบว่า "โดเมน X ชี้ NS มาตามที่คาดหรือยัง" ใช้ dnspython, ตั้งค่าผ่าน `PLOT_RESOLVER` (ค่าเริ่มต้น `192.168.1.175`) และ `PLOT_REGISTRY_ADDR` (`192.168.1.175:5300`)

อัลกอริทึม
1. normalize ชื่อ (R-NAME-01) และ `expected` ทุกตัว; เทียบแบบ **set**
2. ถาม **registry view** (`NS` +norec) → ชุด `parent_ns` (ว่าง = ไม่มี delegation; NXDOMAIN แยกกรณี)
3. ถามผ่าน resolver (`NS`) → ชุด `resolver_ns`
4. สำหรับแต่ละ NS ใน `parent_ns`: resolve ที่อยู่ แล้วถามตรง `SOA <domain>` แบบ `+norec` (timeout 3 วิ, retry 1) เพื่อตรวจว่าตอบจริง (authoritative, AA=1)
5. ผลลัพธ์ (enum) — เรียงลำดับตัดสิน:
   `NXDOMAIN` → ไม่มีชื่อใน registry · `NOT_DELEGATED` → มีชื่อแต่ไม่มี NS · `MISMATCH` → ไม่มี NS ที่คาดเลย · `PARTIAL` → มีบางตัว · `LAME` → NS ครบแต่มีตัวที่ไม่ตอบ/ไม่ authoritative · `VERIFIED` → NS ครบตรงชุดคาด และตอบครบ · `ERROR` → resolver/registry ติดต่อไม่ได้
6. ผลมี `evidence` (parent_ns, resolver_ns, per-NS probe) เพื่อให้ UI ของ hosting แสดงเหตุผลได้

ข้อสังเกตเชิงออกแบบ (ข้อมูลสำหรับระบบ hosting ไม่ใช่งานของ repo นี้): ควร re-verify เป็นระยะด้วย backoff และถอนสถานะเมื่อกลับเป็น MISMATCH

---

## 12. Web UI และ WHOIS/RDAP (optional modules)

### 12.1 Web UI (P6)
Jinja2 + HTMX, ไม่มี SPA/Node build · หน้า: รายการโดเมน, รายละเอียดโดเมน (NS ใน DB vs `dns_visible` พร้อมนับถอยหลัง pending, ปุ่ม hold/renew/expire-now/override), รายการ host, settings, scenarios (รัน + ดูผล), ประวัติเหตุการณ์ · ใช้ API ภายในเดียวกัน ห้ามมี logic ธุรกิจใน template

### 12.2 RDAP/WHOIS (P7)
- `GET /rdap/domain/{name}` (JSON แบบย่อ: name, status, events registration/expiration, nameservers)
- WHOIS TCP 43 แบบข้อความธรรมดา
- ข้อมูลมาจาก DB (เปลี่ยนทันที ไม่รอ delay — D-007)
- transfer-out ด้วย `auth_code` และ virtual clock เป็นงาน optional ของ P7

---

## 13. Config

### 13.1 `.env` (ตัวอย่างใน `.env.example`)
`BIND_ADDR=192.168.1.175` · `API_KEY=change-me` · `SUBNET=172.28.0.0/24` · `PDNS_ROOT_IP=172.28.0.10` · `PDNS_API_KEY=change-me` · `UPSTREAM_DNS=1.1.1.1` · `CACHE_MAX_TTL=3600` · `DATA_DIR=./data`

### 13.2 `config/tlds.yml` (ค่าเริ่มต้น)
```yaml
suffixes:
  com: {min_ns: 2}
  net: {min_ns: 2}
  org: {min_ns: 2}
  info: {min_ns: 2}
  io: {min_ns: 2}
  dev: {min_ns: 2}
  th: {min_ns: 2}
  co.th: {min_ns: 2}
  in.th: {min_ns: 2}
  or.th: {min_ns: 2}
  ac.th: {min_ns: 2}
  go.th: {min_ns: 2}
```

### 13.3 `config/passthrough.txt` (ค่าเริ่มต้น — ปรับตาม Q-004)
```
github.com
githubusercontent.com
pypi.org
pythonhosted.org
docker.io
docker.com
ubuntu.com
debian.org
npmjs.org
cloudflare.com
```

### 13.4 `settings.default.yml`
`propagation_delay: 0` · `ns_ttl: 300` · `default_years: 1` · `expiry_grace_days: 30` · `flush_on_apply: true`

---

## 14. กลยุทธ์ทดสอบ

| ระดับ | ที่อยู่ | ต้องใช้ | ทดสอบอะไร |
|---|---|---|---|
| unit | `tests/unit` | ไม่ต้องมี DB จริงนอก SQLite in-memory | R-NAME, R-DOM, R-HOST, R-NS, projector (R-PUB-01..04) |
| api | `tests/api` | FastAPI TestClient + Fake ports | error envelope, status code, OpenAPI snapshot, flow ต่อ endpoint |
| integration | `tests/integration` (`-m integration`) | **Docker** | zone ใน pdns, การ resolve ผ่าน Unbound, delay, flush, reconcile, `dig`-equivalent ผ่าน dnspython |
| scenarios | `tests/scenarios` | Docker | S01–S16 ผ่าน verifier |

กฎ
- ชื่อ test: `test_R_NAME_03_rejects_subdomain` (มีรหัสกติกา)
- ห้ามใช้ `sleep` จริงใน unit/api: ใช้ `FakeClock`; integration ใช้ polling-with-timeout (≤ 30 วิ) ไม่ใช่ sleep ตายตัว
- coverage ขั้นต่ำ: `core/` และ `services/` ≥ 90%, `dns/projector.py` 100% ของ branch
- integration test ต้อง **พิสูจน์** ข้อกำหนด §7.2 ทุกข้อ เช่น test ที่ glue เป็น `192.168.x.x` แล้ว resolve ได้ (พิสูจน์ว่าไม่มี private-address filter)
- Makefile targets: `make install`, `make lint`, `make test`, `make test-integration`, `make up`, `make down`, `make smoke`, `make fmt`

---

## 15. ความปลอดภัยและการปฏิบัติการ

- bind เฉพาะ `BIND_ADDR`; Unbound `access-control` จำกัด RFC1918 (ไม่เป็น open resolver)
- API key เดียวจาก `.env` เทียบแบบ constant-time; log ห้ามพิมพ์ key
- pdns API และ unbound-control เข้าถึงได้เฉพาะ network ภายในของ compose
- log เป็น JSON หนึ่งบรรทัดต่อเหตุการณ์ มี `request_id` ส่งต่อไปยัง `events`
- backup = คัดลอก `DATA_DIR` (SQLite + pdns sqlite) เอกสารใน RUNBOOK
- ระบบนี้สำหรับ dev LAN เท่านั้น ห้ามเปิดสู่อินเทอร์เน็ต (ระบุใน README และ RUNBOOK)

---

## 16. Phases (0 → 100%)

ทุก phase มี **Exit Gate**: ต้องผ่านครบทุกข้อพร้อมหลักฐานใน PROGRESS จึงถือว่าจบ

### Phase 0 — วางรากฐาน (0 → 5%)
- เป้าหมาย: repo พร้อมทำงาน, ตกลง decision ที่ค้าง
- อ่าน: §2, §3, §4
- ส่งมอบ: `pyproject.toml`, `Makefile`, ruff/mypy/pytest config, `.gitignore`, `.env.example`, CI (GitHub Actions: lint + unit), `README.md` แบบสั้น, บันทึกสภาพแวดล้อม
- Exit Gate:
  - [ ] `make install && make lint && make test` ผ่านบน repo เปล่า (test หนึ่งตัวขึ้นไป)
  - [ ] PROGRESS มีผลตรวจ Python version และ Docker availability
  - [ ] ผู้ใช้ตอบ Q-001..Q-006 และ Decision ที่เกี่ยวข้องถูกอัปเดตเป็น CONFIRMED (โดยผู้ใช้)

### Phase 1 — แกนโดเมน (5 → 20%)
- เป้าหมาย: กติกาธุรกิจทั้งหมดทำงานได้ใน Python ล้วน (ไม่มี HTTP/DNS)
- อ่าน: §4.4, §5, §6
- ส่งมอบ: `core/*`, `db/*` + migration, `services/*` (domains, hosts, nameservers, lifecycle, events), `ports.py`, fakes
- Exit Gate:
  - [ ] ทุก R-NAME/R-DOM/R-HOST/R-NS มี test อย่างน้อย 1 ตัว (ตรวจด้วย script ที่ grep รหัสกติกา)
  - [ ] coverage `core/`+`services/` ≥ 90%
  - [ ] `services/` ไม่ import `api|cli|web|dns` (มี test import-linter แบบง่าย)

### Phase 2 — Registrar API (20 → 35%)
- เป้าหมาย: REST API ตาม §8 ครบ ทำงานกับ Fake ports
- อ่าน: §8
- ส่งมอบ: `api/*`, error envelope, auth, OpenAPI snapshot
- Exit Gate:
  - [ ] ทุก endpoint ใน §8.2 มี API test (happy + อย่างน้อย 1 error)
  - [ ] ทุก error code ใน §8.1 มี test ที่ทำให้เกิดได้จริง
  - [ ] OpenAPI snapshot test ผ่าน
  - [ ] ไม่มี endpoint นอก §8.2

### Phase 3 — DNS จริง (35 → 55%)
- เป้าหมาย: จดโดเมนแล้ว `dig` เห็นผลผ่าน Unbound
- อ่าน: §6.5, §7, §4.3
- ส่งมอบ: `dns/*`, `deploy/*` (compose, unbound, pdns), `plot seed provider`, integration tests
- Exit Gate:
  - [ ] projector ทดสอบ R-PUB-01..07 ครบ (unit, 100% branch)
  - [ ] `make up` ขึ้นครบทุก service และ `/health` = ok
  - [ ] integration: จด+ตั้ง NS → `dig @resolver NS` ถูกต้อง, glue private IP resolve ได้, NXDOMAIN ก่อนจด, delay ทำงาน, flush ทำงาน, reconcile หลัง restart
  - [ ] ถ้ารัน docker ไม่ได้: ระบุ `NOT RUN` และรอผู้ใช้ยืนยันผล (§2.9)

### Phase 4 — CLI (55 → 65%)
- อ่าน: §9
- ส่งมอบ: `plot` ครบตาม §9 (ยกเว้น `scenario`, `verify`, `demo-ns`)
- Exit Gate:
  - [ ] ทุกคำสั่งมี test (typer `CliRunner` กับ API test client)
  - [ ] `--json` ทุกคำสั่ง, exit code ตาม §9
  - [ ] `plot --help` ครบและตรงกับ §9

### Phase 5 — สถานการณ์และตัวตรวจ (65 → 78%)
- อ่าน: §10, §11
- ส่งมอบ: scenario engine + S01–S16, reference verifier, `demo-ns`, `plot verify|scenario|demo-ns`
- Exit Gate:
  - [ ] verifier มี unit test ครบทุกค่า enum (ใช้ fake DNS responses)
  - [ ] `plot scenario run --all` ผ่านทุกข้อบน compose (หรือ `NOT RUN` ตาม §2.9)
  - [ ] S06 พิสูจน์ delay จริงด้วยเวลาที่วัดได้ ±3 วินาที

### Phase 6 — Web UI (78 → 88%)
- อ่าน: §12.1
- ส่งมอบ: หน้าตาม §12.1
- Exit Gate:
  - [ ] ทุกหน้าโหลดได้ (smoke test ผ่าน TestClient)
  - [ ] การกระทำทุกอย่างใน UI เรียก API เดียวกับ CLI (ไม่มี logic ซ้ำ)
  - [ ] ถ่าย screenshot ด้วย Chromium (ถ้ามี) แนบใน PROGRESS

### Phase 7 — โมดูลเสริม (88 → 94%)
- อ่าน: §12.2
- ส่งมอบ (ทำเฉพาะข้อที่ผู้ใช้เลือก): RDAP, WHOIS, transfer ด้วย auth code, virtual clock
- Exit Gate: แต่ละโมดูลที่เลือกมี test และเอกสารใน README; โมดูลที่ไม่เลือกต้องไม่มีโค้ดค้าง

### Phase 8 — ปิดงาน (94 → 100%)
- อ่าน: §15, §17, §18
- ส่งมอบ: `README.md`, `docs/RUNBOOK.md` (ติดตั้งบน 192.168.1.175, ตั้ง DNS client, แก้ systemd-resolved, troubleshooting ด้วย `dig +trace`/registry view, backup), ปรับแต่ง log/health, tag `v1.0.0`
- Exit Gate:
  - [ ] Acceptance checklist §18 ผ่านทุกข้อโดยผู้ใช้
  - [ ] RUNBOOK ทดลองทำตามตั้งแต่เครื่องเปล่าได้จริง (ผู้ใช้ยืนยัน)
  - [ ] ไม่มีรายการ "Unverified" ค้างใน PROGRESS

---

## 17. การติดตั้งบน 192.168.1.175 (สรุป; รายละเอียดใน RUNBOOK ที่เขียนใน P8)

1. ติดตั้ง Docker + compose plugin
2. Ubuntu: ตั้ง `DNSStubListener=no` ใน `/etc/systemd/resolved.conf` แล้ว restart `systemd-resolved`
3. `cp .env.example .env` แก้ค่า (โดยเฉพาะ `API_KEY`, `PDNS_API_KEY`) · `make up`
4. `plot seed provider --domain myhost.net --ns1-ip <IP> --ns2-ip <IP>`
5. ตั้ง DNS ของเครื่อง dev: ผ่าน DHCP option ของ router หรือรายเครื่อง
6. firewall: อนุญาต 53, 5300, 8080 จาก LAN เท่านั้น
7. เครื่อง/container ของระบบ hosting ที่ต้องใช้ sandbox ให้ตั้ง resolver เป็น `192.168.1.175` ชัดเจน (เช่น `dns:` ใน compose ของ hosting) และปิด DNS-over-HTTPS ในเบราว์เซอร์ตอนทดสอบ

หมายเหตุ seed provider: โดเมน `myhost.net` ต้องจดใน sandbox และ nameserver จริงของ provider (`demo-ns` หรือของ hosting จริง) ต้องให้บริการ zone `myhost.net` ที่มี A ของ `ns1`/`ns2` ไม่เช่นนั้น Unbound จะ resolve ชื่อ NS ของลูกค้าไม่ได้

---

## 18. Acceptance checklist (ผู้ใช้ตรวจจากเครื่อง dev ที่ตั้ง DNS = 192.168.1.175)

- [ ] `dig <ชื่อที่ไม่เคยจด>.com` → NXDOMAIN
- [ ] `dig github.com` → resolve ได้ (passthrough)
- [ ] จดโดเมนใหม่, ตั้ง NS → `dig <domain> NS` ตรง (หลัง delay ที่ตั้ง)
- [ ] child NS + glue (IP 192.168.x.x) → `dig +trace <domain>` เดินผ่าน glue ได้
- [ ] เปลี่ยน NS แล้ว resolver เห็นค่าใหม่หลัง delay/flush
- [ ] `plot scenario run --all` → S01–S16 ผ่าน
- [ ] `plot verify` ให้ผลครบทุก enum ในสถานการณ์ที่เกี่ยวข้อง
- [ ] ระบบ hosting จริงชี้ resolver มาที่ sandbox แล้วทำ flow add domain → verify ได้ครบ
- [ ] `plot admin reset --all` แล้วเริ่มทดสอบรอบใหม่ได้ภายใน 1 นาที
- [ ] restart ทั้ง compose แล้วข้อมูลและ DNS กลับมาถูกต้อง (reconcile)

---

## 19. Changelog ของ SPEC
- v0.1 — ร่างแรก (รอผู้ใช้ยืนยัน §3)

---

## ภาคผนวก A — เทมเพลตรายงาน (ใช้ทุกครั้งที่หยุด)

```
## รายงาน: <Task/Phase ID>
**เสร็จแล้ว:** <รายการสั้น ๆ>
**หลักฐาน:** <คำสั่ง + ผลสรุปจริง เช่น "make test → 84 passed, 0 failed">
**NOT RUN / Unverified:** <สิ่งที่ไม่ได้รัน/ตรวจ พร้อมเหตุผล>
**เบี่ยงจาก SPEC:** <ไม่มี | รายการ + Spec Change Request ID>
**Assumptions ใหม่:** <A-xxx ...>
**คำถามค้าง:** <ไม่มี | คำถาม + คำแนะนำ 1 ทาง>
**ถัดไป:** <task/phase ถัดไป และรออนุมัติหรือไม่>
```

## ภาคผนวก B — ข้อความเริ่มงาน (ผู้ใช้คัดลอกไปใช้)

- เริ่ม phase: `อ่าน CLAUDE.md, docs/SPEC.md, docs/PROGRESS.md แล้วทำ Phase <n> ตามเอกสาร ทีละ task จนครบ Exit Gate แล้วหยุดรายงานตามภาคผนวก A`
- ทำต่อ: `อ่าน docs/PROGRESS.md แล้วทำ task ถัดไปตาม SPEC`
- ตรวจงาน: `ตรวจ Exit Gate ของ Phase <n> เทียบกับ SPEC §16 ทีละข้อ แล้วรายงานข้อที่ไม่ผ่านพร้อมหลักฐาน อย่าแก้โค้ด`
- เปลี่ยนโหมด: `ตั้ง autonomy: continuous ใน PROGRESS`

## ภาคผนวก C — อภิธานศัพท์
- **Registry**: ผู้ถือ zone ของ TLD (ในระบบนี้คือ zone `.` ใน pdns)
- **Registrar**: ผู้รับจดทะเบียน (REST/CLI/UI ของระบบนี้)
- **Delegation**: NS record ที่ parent ชี้ว่าโดเมนนี้ใครดูแล
- **Glue**: A/AAAA ของ nameserver ที่อยู่ใต้โดเมนที่มันดูแลเอง ใส่ที่ parent เพื่อกัน circular dependency
- **Host (child nameserver)**: ชื่อ nameserver ที่ลงทะเบียนในระบบ (subordinate = มีโดเมนแม่ในระบบ, external = ไม่มี)
- **In-bailiwick**: NS ที่ชื่ออยู่ใต้โดเมนที่มันดูแล
- **Lame delegation**: delegate ไปหา nameserver ที่ไม่ตอบหรือไม่ authoritative
- **Registry view**: คำตอบของ pdns-root ที่พอร์ต 5300 (delegation จาก parent โดยตรง ไม่ผ่าน cache)
