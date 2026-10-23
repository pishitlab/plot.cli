# RUNBOOK — Domain Sandbox บน 192.168.1.175

ขั้นตอนติดตั้ง ใช้งาน แก้ปัญหา และ backup (SPEC §15, §17) · เขียนสำหรับ Ubuntu LTS (PROGRESS A-002)

> ⚠️ ระบบนี้สำหรับ **dev LAN เท่านั้น** ห้ามเปิดพอร์ตใด ๆ สู่อินเทอร์เน็ต

เครื่องหมาย `$C` ในเอกสารนี้หมายถึง (รันที่ root ของ repo):

```sh
C="docker compose --env-file .env --project-directory . -f deploy/docker-compose.yml"
```

## 1. เตรียมเครื่อง

1. ติดตั้ง Docker Engine + compose plugin ตามเอกสารทางการ: <https://docs.docker.com/engine/install/ubuntu/>
   ตรวจ: `docker version` และ `docker compose version` (ทดสอบแล้วกับ Engine 29.9.1, Compose v5.6.0) ·
   ผู้ใช้ที่รันต้องอยู่กลุ่ม `docker` (`sudo usermod -aG docker $USER` แล้ว login ใหม่) หรือใช้ `sudo`
2. ติดตั้ง `make`, `git`, `curl` (`sudo apt install make git curl`)
3. พอร์ต 53/5300/8080 บน `BIND_ADDR` ต้องว่าง — `make deploy` ตรวจให้และหยุดพร้อมบอกพอร์ตที่ชน ·
   systemd-resolved ของ Ubuntu ฟังที่ `127.0.0.53`/`127.0.0.54` เท่านั้น จึง**ไม่ชน**กับ `BIND_ADDR=192.168.1.175`
   ถ้า preflight แจ้งว่าพอร์ต 53 ถูกใช้ ให้ดูว่าใคร: `sudo ss -lntup 'sport = :53'` แล้วหยุดบริการนั้น
   (เช่น `dnsmasq`, `bind9`) · กรณีที่เป็น systemd-resolved จริง (ตั้ง `DNSStubListenerExtra` ไว้) :
   ```sh
   sudo sed -i 's/^#\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
   sudo systemctl restart systemd-resolved
   sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf   # เครื่องนี้ยัง resolve ชื่อได้
   ```
4. Firewall — **กับดัก**: พอร์ตที่ Docker publish **ไม่ผ่านกฎของ `ufw`** (Docker ใส่กฎ iptables ของตัวเองก่อน)
   การ `ufw deny` จึงไม่ได้ปิดอะไร ด่านจริงคือ:
   - `BIND_ADDR` = IP ใน LAN (preflight ห้าม `0.0.0.0`) และ router **ไม่ forward** พอร์ต 53/5300/8080 จากอินเทอร์เน็ต
   - ถ้าต้องจำกัดต้นทางเพิ่ม ให้ใส่กฎใน chain `DOCKER-USER` ตามเอกสาร Docker
     (<https://docs.docker.com/engine/network/packet-filtering-firewalls/>) เช่น ทิ้งการเชื่อมต่อใหม่ที่ไม่ได้มาจาก LAN:
     `sudo iptables -I DOCKER-USER -i <iface> ! -s 192.168.0.0/16 -m conntrack --ctstate NEW -j DROP`
     (ยังไม่ได้ทดสอบบน 192.168.1.175 — PROGRESS U-006)

## 2. ติดตั้งและเปิดระบบ

```sh
git clone <repo> plot.cli && cd plot.cli
BIND_ADDR=192.168.1.175 make deploy
```

`make deploy` (`scripts/deploy.sh`) ทำตามลำดับ และหยุดทันทีพร้อมข้อความ `ERROR:` ที่บอกวิธีแก้เมื่อขั้นใดไม่ผ่าน:

1. **preflight** — มี `curl`, Docker daemon ตอบ, Compose v2; `.env`: key ไม่ว่าง/ไม่ใช่ `change-me`/ยาว ≥ 16,
   `BIND_ADDR` ไม่ใช่ `0.0.0.0` และเป็น IP ของเครื่องนี้; พอร์ต 53/5300/8080 ว่าง
2. ถ้ายังไม่มี `.env` → สร้างจาก `.env.example` พร้อม `API_KEY`/`PDNS_API_KEY` สุ่ม 48 hex และ `BIND_ADDR` ที่ส่งมา (mode 600)
   ถ้ามี `.env` แล้ว จะใช้ของเดิม (`BIND_ADDR` ที่ส่งมาต้องตรงกับในไฟล์ ไม่งั้นหยุด) · แก้ค่าอื่นได้ใน `.env` แล้ว `make deploy` ซ้ำ
3. build image (`plot-unbound:local`, `plot-registrar:local`) → start: pdns-root → unbound → registrar ตาม healthcheck
4. รอ `GET /api/v1/health` = `ok` (สูงสุด 3 นาที; ไม่ผ่าน → พิมพ์ `ps` + log 40 บรรทัดล่าสุด)
5. `plot seed provider` (จด `myhost.net`; ใช้ IP ของ ns จริง: `NS1_IP=… NS2_IP=… make deploy`)
6. smoke test 6 ข้อ แล้วพิมพ์ URL ของ API/Web UI

รันซ้ำได้เสมอ (idempotent) · ขึ้นครั้งแรก registrar สร้าง DB (`DATA_DIR/registrar.db`), สร้าง zone `.` ใน pdns-root
และ reconcile ให้ตรงกับ DB · API key อยู่ใน `.env` (`grep ^API_KEY= .env`)

### Seed provider (`myhost.net`)

customer domain ที่ชี้ NS มาที่ `ns1/ns2.myhost.net` จะ resolve ได้ก็ต่อเมื่อ `myhost.net` ถูกจดใน sandbox และ nameserver ของมัน
ให้บริการ zone `myhost.net` อยู่จริง

- ใช้ demo-ns ของ sandbox (ค่าเริ่มต้น, PROGRESS A-001): `make deploy` ทำให้แล้ว (หรือ `make seed`; ns1 → 172.28.0.31, ns2 → 172.28.0.32)
- ใช้ nameserver ของระบบ hosting จริง (เมื่อมี IP แล้ว): `make seed NS1_IP=<IP> NS2_IP=<IP>`
  และ nameserver ตัวจริงต้องเป็น authoritative ของ `myhost.net` และของโดเมนลูกค้าที่ทดสอบ

ให้ demo-ns เป็น authoritative ของโดเมนลูกค้า (เช่นเพื่อให้ verifier ได้ `VERIFIED`):
`$C exec registrar plot demo-ns add-zone shop.com --a 10.0.0.1`

## 3. ตั้ง DNS ให้ client (รายเครื่อง — PROGRESS A-002)

| ที่ใช้ | วิธี |
|---|---|
| Linux (systemd-resolved) | `sudo resolvectl dns <iface> 192.168.1.175 && sudo resolvectl domain <iface> '~.'` |
| macOS | `sudo networksetup -setdnsservers Wi-Fi 192.168.1.175` (คืนค่า: `... Wi-Fi Empty`) |
| Windows | Settings → Network → DNS server assignment → Manual → 192.168.1.175 |
| container ของระบบ hosting | compose: `dns: [192.168.1.175]` ในทุก service ที่ต้องเห็น sandbox |
| เบราว์เซอร์ | ปิด DNS-over-HTTPS (Secure DNS) ระหว่างทดสอบ ไม่งั้นจะข้าม sandbox |

ตรวจจากเครื่อง dev: `dig never-registered-xyz.com` → `NXDOMAIN`; `dig github.com` → ได้ IP (passthrough)

## 4. ใช้งานประจำวัน

- API/UI: `http://192.168.1.175:8080/api/v1/...` และ `http://192.168.1.175:8080/ui/` (login ด้วย `API_KEY`)
- CLI บนเครื่อง dev: `pip install .` แล้ว `export PLOT_API_URL=http://192.168.1.175:8080 PLOT_API_KEY=...`
- Scenario ทั้งหมด: `make scenarios` (~1 นาที)
- ตรวจเร็วว่าระบบตอบถูก: `make smoke`
- เริ่มรอบทดสอบใหม่: `plot admin reset --all` (เก็บ `myhost.net` ที่เป็น seed ไว้)
- สถานะ/log: `make ps` (ทุก service ต้อง `healthy`), `make logs` หรือ `$C logs -f registrar` · log ของ Docker หมุนเอง 10MB × 3 ไฟล์ต่อ service

## 5. แก้ปัญหา

### เครื่องมือ

```sh
dig @192.168.1.175 shop.com NS                       # สิ่งที่ client เห็น (ผ่าน resolver)
dig @192.168.1.175 -p 5300 shop.com NS +norec        # registry view: referral + glue จาก root จำลอง
plot domain info shop.com                            # NS ใน DB vs dns_visible (+ pending)
plot verify shop.com --expect ns1.myhost.net ns2.myhost.net   # evidence ทีละ NS
```

> **`dig +trace` จากเครื่อง dev**: `+trace` ให้ dig คุยกับ root เองโดยตรง แต่ root จำลอง (`a.root-servers.net` = `PDNS_ROOT_IP`
> เช่น 172.28.0.10) เป็น IP ภายใน Docker ที่เครื่องใน LAN โดยทั่วไปเข้าไม่ถึง จึงมักหยุดที่ขั้น root ·
> ทางแทน: ใช้ registry view (`-p 5300 +norec`) ดู referral + glue แล้ว `dig @<glue IP> <domain> SOA +norec` ถามต่อเอง
> (ยังไม่ได้ทดสอบบน 192.168.1.175 — PROGRESS U-005)

### อาการที่พบบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| `make deploy` แจ้ง `tcp/53 is already in use` (หรือ 5300/8080) | มีบริการอื่นฟังพอร์ตนั้นบน `BIND_ADDR` → ข้อ 1.3 |
| `make deploy` แจ้ง `not healthy after 3 minutes` | ดู log ที่พิมพ์ออกมา; `make ps` ดูว่าตัวไหนไม่ `healthy` |
| `make deploy` แจ้ง `BIND_ADDR=… is not an address of this machine` | IP ใน `.env` ไม่ตรงกับเครื่อง (`hostname -I`) → แก้ `.env` |
| `/health` = `degraded`, `pdns: down` | pdns-root ไม่ขึ้นหรือ publish ค้างใน retry: `$C ps`, `$C logs pdns-root registrar`; การเปลี่ยนแปลงยังรออยู่ใน pending และจะถูก apply เองเมื่อ pdns กลับมา |
| `/health` `unbound: down` | `$C logs unbound` (มักเป็น config ผิดตอน render: entrypoint รัน `unbound-checkconf` ก่อนเสมอ) |
| โดเมนที่จดแล้วยัง NXDOMAIN | ไม่มี NS / ติด hold / หมดอายุ / ยังไม่ถึงเวลา delay → ดู `plot domain info` (`dns_visible.pending`) |
| SERVFAIL ตอน resolve ชื่อใต้โดเมน | NS ปลายทางไม่ให้บริการ zone นั้น (lame) → `plot verify` ดู probe; ถ้าใช้ demo-ns ให้ `plot demo-ns add-zone` |
| ชื่อ NS ของ provider resolve ไม่ได้ | ยังไม่ได้ seed `myhost.net` หรือ zone `myhost.net` บน nameserver หาย → seed ซ้ำ |
| เห็นคำตอบเก่าหลังเปลี่ยน NS | `flush_on_apply` ปิดอยู่ หรือ client cache เอง → `plot admin flush <domain>` และล้าง cache ของ OS/เบราว์เซอร์ |
| passthrough (เช่น github.com) ไม่ได้ | เครื่อง 192.168.1.175 ออก `UPSTREAM_DNS` ไม่ได้ → ตรวจ firewall ขาออก udp/tcp 53 |
| client ไม่ผ่าน sandbox เลย | DNS ของเครื่องไม่ได้ชี้ 192.168.1.175, VPN/DoH แทรก → ข้อ 3 |
| client ได้ `REFUSED` | IP ของ client ไม่อยู่ใน RFC1918 (เช่น VPN `100.64.0.0/10`) → เพิ่มใน `.env` `RESOLVER_EXTRA_ALLOW="100.64.0.0/10"` แล้ว `make deploy` |
| `plot seed provider` แจ้ง `HOST_ADDR_FORBIDDEN` | `ns1.myhost.net` ถูกใช้เป็น NS ก่อน seed จึงเป็น external host → `plot admin reset --all` แล้ว seed ใหม่ |

## 6. Backup / restore

ข้อมูลจริงอยู่ที่ `DATA_DIR/registrar.db` (SQLite, WAL) เท่านั้น; ข้อมูลใน pdns-root ถูกสร้างใหม่จาก DB ได้ทุกเมื่อด้วย reconcile
(PROGRESS A-020) จึงเก็บใน Docker volume ไม่ต้อง backup · **อย่า copy `registrar.db` ตรง ๆ ขณะระบบรัน** (ข้อมูลล่าสุดอยู่ใน `-wal`)

```sh
make backup                     # ระหว่างระบบทำงานได้ → พิมพ์ /data/backups/registrar-<UTC>.db (= DATA_DIR/backups/ บนเครื่อง)
cp data/backups/registrar-*.db /somewhere/else/    # เก็บนอกเครื่อง: backups อยู่บนดิสก์เดียวกับ DB

make restore FILE=data/backups/registrar-20261023T034526Z.db
```

`make restore` ตรวจ `PRAGMA integrity_check` ของไฟล์ก่อน (ไม่ผ่าน → หยุดโดยไม่แตะระบบ) → หยุด registrar → ลบ `-wal`/`-shm`
ของ DB เก่า → copy → start และรอ healthy; registrar reconcile zone `.` ให้ตรงกับ DB ที่กู้ทันที · zone ของ demo-ns
(ถ้า volume ถูกลบ) สร้างใหม่ด้วย `make seed` / `plot demo-ns add-zone`

ไฟล์ใน `DATA_DIR` เป็นของ root (เขียนโดย container) — ลบทิ้งต้องใช้ `sudo rm -rf data`

## 7. อัปเดตเวอร์ชัน

```sh
make backup && git pull && make deploy     # build ใหม่; migration ของ DB รันเองตอน registrar เริ่ม
```

registrar ต้องรัน uvicorn **1 worker เท่านั้น** (publisher เป็น thread ใน process; หลาย worker = publisher หลายตัวแย่งกัน)
— อย่าเพิ่ม `--workers` ใน `deploy/registrar/Dockerfile` · เวอร์ชันของ image/แพ็กเกจที่ใช้ดูได้ใน PROGRESS หัวข้อ "Pinned versions"
(base image pin ด้วย digest)

## 8. ข้อจำกัดด้านความปลอดภัย (dev LAN)

- API/Web UI เป็น **HTTP ไม่มี TLS**: API key ใน header และ cookie ของ Web UI (HttpOnly, SameSite=strict) วิ่งบน LAN แบบอ่านได้
  → ใช้ key เฉพาะ sandbox นี้, เปลี่ยนได้โดยแก้ `API_KEY` ใน `.env` แล้ว `make deploy`
- key เดียวมีสิทธิ์ทั้งหมด (ไม่มี user/role ตาม SPEC) · `.env` เป็น mode 600 และอยู่ใน `.gitignore`
- resolver รับ query จาก RFC1918 (+ `RESOLVER_EXTRA_ALLOW`) เท่านั้น; ไม่มี DNS ใดออกนอกเครื่องยกเว้น passthrough ไป `UPSTREAM_DNS`
  (pdns ปิด security polling แล้ว)
- firewall: ดูกับดัก `ufw` ในข้อ 1.4
