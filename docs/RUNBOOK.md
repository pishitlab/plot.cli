# RUNBOOK — Domain Sandbox บน 192.168.1.175

ขั้นตอนติดตั้ง ใช้งาน แก้ปัญหา และ backup (SPEC §15, §17) · เขียนสำหรับ Ubuntu LTS (PROGRESS A-002)

> ⚠️ ระบบนี้สำหรับ **dev LAN เท่านั้น** ห้ามเปิดพอร์ตใด ๆ สู่อินเทอร์เน็ต

เครื่องหมาย `$C` ในเอกสารนี้หมายถึง (รันที่ root ของ repo):

```sh
C="docker compose --env-file .env --project-directory . -f deploy/docker-compose.yml"
```

## 1. เตรียมเครื่อง

1. ติดตั้ง Docker Engine + compose plugin ตามเอกสารทางการ: <https://docs.docker.com/engine/install/ubuntu/>
   ตรวจ: `docker version` และ `docker compose version` (ทดสอบแล้วกับ Engine 29.9.1, Compose v5.6.0)
2. ติดตั้ง `make` และ `git` (`sudo apt install make git`)
3. **ปลดพอร์ต 53 จาก systemd-resolved** (มันจอง `127.0.0.53:53` อยู่):
   ```sh
   sudo sed -i 's/^#\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
   sudo systemctl restart systemd-resolved
   # เครื่องนี้เองยังต้อง resolve ชื่อได้: ชี้ /etc/resolv.conf ไปที่ไฟล์ที่ไม่ใช่ stub
   sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
   sudo ss -lunp | grep ':53 '        # ต้องไม่เหลือใครฟังพอร์ต 53
   ```
4. Firewall: อนุญาต 53/udp, 53/tcp, 5300/udp, 5300/tcp, 8080/tcp จาก LAN เท่านั้น เช่น `ufw`:
   ```sh
   for p in 53/udp 53/tcp 5300/udp 5300/tcp 8080/tcp; do sudo ufw allow from 192.168.0.0/16 to any port ${p%/*} proto ${p#*/}; done
   ```

## 2. ติดตั้งและเปิดระบบ

```sh
git clone <repo> plot.cli && cd plot.cli
cp .env.example .env
# แก้ .env: BIND_ADDR=192.168.1.175, API_KEY และ PDNS_API_KEY เป็นค่าสุ่มยาว ๆ เช่น `openssl rand -hex 24`
make up                                   # build image + start 5 service
curl http://192.168.1.175:8080/api/v1/health
# {"status":"ok","db":"ok","pdns":"ok","unbound":"ok"}
make smoke ENV_FILE=.env                  # ตรวจเร็วว่าระบบตอบถูก
```

ขึ้นครั้งแรก registrar จะสร้าง DB (`DATA_DIR/registrar.db`), สร้าง zone `.` ใน pdns-root และ reconcile ให้ตรงกับ DB

### Seed provider (`myhost.net`)

customer domain ที่ชี้ NS มาที่ `ns1/ns2.myhost.net` จะ resolve ได้ก็ต่อเมื่อ `myhost.net` ถูกจดใน sandbox และ nameserver ของมัน
ให้บริการ zone `myhost.net` อยู่จริง

- ใช้ demo-ns ของ sandbox (ค่าเริ่มต้น, PROGRESS A-001):
  ```sh
  $C exec registrar plot seed provider          # ns1 → 172.28.0.31, ns2 → 172.28.0.32
  ```
- ใช้ nameserver ของระบบ hosting จริง (เมื่อมี IP แล้ว): `$C exec registrar plot seed provider --ns1-ip <IP> --ns2-ip <IP>`
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

- API/UI: `http://192.168.1.175:8080/api/v1/...` และ `http://192.168.1.175:8080/ui/`
- CLI บนเครื่อง dev: `pip install .` แล้ว `export PLOT_API_URL=http://192.168.1.175:8080 PLOT_API_KEY=...`
- Scenario ทั้งหมด: `$C exec registrar plot scenario run --all` (~1 นาที)
- เริ่มรอบทดสอบใหม่: `plot admin reset --all` (เก็บ `myhost.net` ที่เป็น seed ไว้)
- ดู log: `$C logs -f registrar` (unbound: `$C logs -f unbound`)

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
| `make up` แจ้ง port 53 ถูกใช้ | systemd-resolved ยังฟังอยู่ → ทำข้อ 1.3 |
| `/health` = `degraded`, `pdns: down` | pdns-root ไม่ขึ้นหรือ publish ค้างใน retry: `$C ps`, `$C logs pdns-root registrar`; การเปลี่ยนแปลงยังรออยู่ใน pending และจะถูก apply เองเมื่อ pdns กลับมา |
| `/health` `unbound: down` | `$C logs unbound` (มักเป็น config ผิดตอน render: entrypoint รัน `unbound-checkconf` ก่อนเสมอ) |
| โดเมนที่จดแล้วยัง NXDOMAIN | ไม่มี NS / ติด hold / หมดอายุ / ยังไม่ถึงเวลา delay → ดู `plot domain info` (`dns_visible.pending`) |
| SERVFAIL ตอน resolve ชื่อใต้โดเมน | NS ปลายทางไม่ให้บริการ zone นั้น (lame) → `plot verify` ดู probe; ถ้าใช้ demo-ns ให้ `plot demo-ns add-zone` |
| ชื่อ NS ของ provider resolve ไม่ได้ | ยังไม่ได้ seed `myhost.net` หรือ zone `myhost.net` บน nameserver หาย → seed ซ้ำ |
| เห็นคำตอบเก่าหลังเปลี่ยน NS | `flush_on_apply` ปิดอยู่ หรือ client cache เอง → `plot admin flush <domain>` และล้าง cache ของ OS/เบราว์เซอร์ |
| passthrough (เช่น github.com) ไม่ได้ | เครื่อง 192.168.1.175 ออก `UPSTREAM_DNS` ไม่ได้ → ตรวจ firewall ขาออก udp/tcp 53 |
| client ไม่ผ่าน sandbox เลย | DNS ของเครื่องไม่ได้ชี้ 192.168.1.175, VPN/DoH แทรก → ข้อ 3 |
| `plot seed provider` แจ้ง `HOST_ADDR_FORBIDDEN` | `ns1.myhost.net` ถูกใช้เป็น NS ก่อน seed จึงเป็น external host → `plot admin reset --all` แล้ว seed ใหม่ |

## 6. Backup / restore

ข้อมูลจริงอยู่ที่ `DATA_DIR/registrar.db` (SQLite) เท่านั้น; ข้อมูลใน pdns-root ถูกสร้างใหม่จาก DB ได้ทุกเมื่อด้วย reconcile
(PROGRESS A-020) จึงเก็บใน Docker volume ไม่ต้อง backup

```sh
# backup (ระหว่างระบบทำงานได้)
$C exec registrar python -c "import sqlite3; s=sqlite3.connect('/data/registrar.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
cp data/backup.db backups/registrar-$(date +%F).db

# restore
make down
cp backups/registrar-YYYY-MM-DD.db data/registrar.db
make up                     # registrar reconcile zone "." ให้ตรงกับ DB ตอนเริ่ม
$C exec registrar plot seed provider     # zone ของ demo-ns (ถ้า volume ถูกลบ) สร้างใหม่ด้วย seed / add-zone
```

## 7. อัปเดตเวอร์ชัน

```sh
git pull && make up         # build ใหม่; migration ของ DB รันเองตอน registrar เริ่ม
```

เวอร์ชันของ image/แพ็กเกจที่ใช้ดูได้ใน PROGRESS หัวข้อ "Pinned versions"
