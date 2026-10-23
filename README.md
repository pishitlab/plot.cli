# plot.cli — Domain Sandbox

"อินเทอร์เน็ตจำลอง" สำหรับทดสอบ flow **add domain → ลูกค้าตั้ง nameserver → ระบบตรวจว่า NS ชี้มาหาเรา → ยืนยันความเป็นเจ้าของ**
ของระบบ hosting ได้ซ้ำ ๆ โดยไม่ต้องใช้โดเมนจริงหรือ IP จริง

> ⚠️ **สำหรับ dev LAN เท่านั้น — ห้ามเปิดสู่อินเทอร์เน็ต** (ไม่มี user/role, API key เดียว, resolver รับเฉพาะ RFC1918)

| เอกสาร | เนื้อหา |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | สเปก: สถาปัตยกรรม, กติกาธุรกิจ, API/CLI contract, scenario |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | ติดตั้งบน `192.168.1.175`, ตั้ง DNS ให้ client, แก้ปัญหา, backup |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | สถานะงาน, หลักฐาน, สมมติฐาน (A-xxx), เวอร์ชันที่ pin |

## ส่วนประกอบ

```
เครื่อง dev / ระบบ hosting ──DNS:53──▶ 192.168.1.175 (Docker Compose)
  unbound    172.28.0.2   :53   resolver ที่ client ใช้ (เดินจาก root จำลองเท่านั้น)
  pdns-root  172.28.0.10  :5300 registry = zone "." (delegation + glue ของทุกโดเมนที่จด)
  registrar  172.28.0.20  :8080 REST API + Web UI + publisher (SQLite ใน DATA_DIR)
  demo-ns1/2 172.28.0.31/.32    nameserver ของ "provider" จำลอง (myhost.net)
```

- **ชื่อที่ไม่ได้จด → NXDOMAIN** ยกเว้นโดเมนใน [`config/passthrough.txt`](config/passthrough.txt) ที่ forward ไป DNS จริง (และจดใน sandbox ไม่ได้)
- จดได้เฉพาะ 1 label + suffix ใน [`config/tlds.yml`](config/tlds.yml) (เช่น `shop.com`, `shop.co.th`)
- DB เปลี่ยนทันที แต่ DNS เปลี่ยนหลัง `propagation_delay` (ตั้งได้ทั้งระบบหรือรายโดเมน) — ดูได้ที่ `dns_visible`

## ติดตั้ง (สรุป — รายละเอียดใน [RUNBOOK](docs/RUNBOOK.md))

```sh
cp .env.example .env          # ตั้ง BIND_ADDR, API_KEY, PDNS_API_KEY (สุ่มยาว ๆ)
make up                       # build + start ทั้ง 5 service
curl http://192.168.1.175:8080/api/v1/health      # {"status":"ok",...}
docker compose --env-file .env --project-directory . -f deploy/docker-compose.yml \
  exec registrar plot seed provider               # จด myhost.net + ns1/ns2 บน demo-ns
```

จากนั้นตั้ง DNS ของเครื่อง dev / container ของระบบ hosting เป็น `192.168.1.175` (ดู RUNBOOK §3)

## ใช้งาน

### CLI `plot`

ติดตั้งบนเครื่อง dev: `pip install .` (Python 3.12) แล้วตั้ง

```sh
export PLOT_API_URL=http://192.168.1.175:8080 PLOT_API_KEY=<API_KEY>
plot domain register shop.com --ns ns1.myhost.net --ns ns2.myhost.net
plot domain info shop.com                 # NS ใน DB vs สิ่งที่ DNS เห็น + pending
plot host create ns1.shop.com --ipv4 192.168.1.50      # child NS + glue
plot ns set shop.com ns1.shop.com ns2.myhost.net
plot override shop.com --delay 20          # หรือ none
plot domain hold shop.com | release shop.com | expire-now shop.com
plot admin settings --delay 0 --ttl 300
plot admin flush shop.com
plot admin reset --prefix scn-             # หรือ --all (โดเมน seed ไม่ถูกลบ)
```

ทุกคำสั่งรับ `--json`; exit code 0 = สำเร็จ, 1 = error จาก API (พิมพ์ `CODE: message`), 2 = ใช้คำสั่งผิด

คำสั่งที่ต้องเข้าถึงภายใน compose (`seed`, `demo-ns`, `scenario`) ให้รันใน container registrar:
`docker compose ... exec registrar plot <คำสั่ง>` (env ถูกตั้งไว้แล้ว)

### Web UI

`http://192.168.1.175:8080/ui/` — login ด้วย `API_KEY` · หน้ารายการโดเมน, รายละเอียด (DB vs DNS พร้อมนับถอยหลัง pending), hosts, settings, scenarios, history ·
ทุกปุ่มเรียก REST API เดียวกับ CLI ([ภาพหน้าจอ](docs/screenshots/))

### Reference verifier (ตัวอย่างสำหรับระบบ hosting)

```sh
PLOT_RESOLVER=192.168.1.175 PLOT_REGISTRY_ADDR=192.168.1.175:5300 \
  plot verify shop.com --expect ns1.myhost.net ns2.myhost.net
```

ผลเป็นหนึ่งใน `VERIFIED` `PARTIAL` `MISMATCH` `LAME` `NOT_DELEGATED` `NXDOMAIN` `ERROR` พร้อม evidence
(registry view, คำตอบ resolver, ผล probe SOA ของแต่ละ NS) — อัลกอริทึมใน SPEC §11; การแยก
`NOT_DELEGATED` กับ `NXDOMAIN` ต้องถาม registrar API เพิ่ม เพราะทาง DNS ตอบเหมือนกัน (PROGRESS A-025)

### Scenario catalog (S01–S16)

```sh
docker compose ... exec registrar plot scenario list
docker compose ... exec registrar plot scenario run --all      # ~1 นาที, cleanup เอง
```

## Config

| ไฟล์/ตัวแปร | ความหมาย |
|---|---|
| `.env` `BIND_ADDR` | IP ที่ publish พอร์ต 53/5300/8080 (ห้าม `0.0.0.0` บนเครื่องที่ออกเน็ตตรง) |
| `.env` `API_KEY`, `PDNS_API_KEY` | key ของ registrar API และ pdns API (ภายใน) — ต้องตั้งเสมอ |
| `.env` `SUBNET`, `PDNS_ROOT_IP`, `*_IP` | network ภายใน compose (ค่าเริ่มต้นตาม SPEC §4.1) |
| `.env` `UPSTREAM_DNS`, `CACHE_MAX_TTL`, `DATA_DIR` | upstream ของ passthrough, TTL สูงสุดใน cache, ที่เก็บ `registrar.db` |
| `config/tlds.yml` · `config/passthrough.txt` · `config/settings.default.yml` | suffix ที่จดได้ · โดเมนจริงที่ forward · ค่าเริ่มต้น runtime settings |

## พัฒนา / ทดสอบ

```sh
make install          # .venv + dev tools
make lint             # ruff + mypy --strict
make test             # unit + api + cli + web (coverage gate core/services ≥ 90%, projector 100%)
make up && make test-integration      # ต้องมี Docker: integration + scenario บน stack จริง
make smoke            # ตรวจ stack ที่รันอยู่แบบเร็ว (health, NXDOMAIN, passthrough, myhost.net)
make fmt | make down
```
