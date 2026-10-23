# Review ก่อน deploy — 2026-10-23

ผู้ตรวจ: AI (ตามคำสั่งผู้ใช้ "ไล่จาก code → ทำรายงาน → ตรวจแบบมืออาชีพ → ทำให้สมบูรณ์จน git ไป deploy ได้ในครั้งเดียว")
ขอบเขต: โค้ดใน `src/`, `deploy/`, `Makefile`, CI, `docs/RUNBOOK.md` ที่ commit `98bc018`
วิธีตรวจ: อ่านเส้นทาง runtime ทั้งหมด (API → services → publisher/worker → pdns/unbound, Web UI, CLI, deploy) แล้วยืนยันแต่ละข้อด้วยการค้นในโค้ด

ระดับ: **สูง** = ทำให้ deploy ครั้งเดียวไม่ชัวร์ / ระบบหยุดทำงาน / ความปลอดภัย · **กลาง** = เสื่อมเมื่อใช้นาน หรือผลไม่ตรงในกรณีขอบ · **ต่ำ** = เอกสาร/ข้อจำกัดที่ต้องรู้

## ข้อค้นพบ

| ID | ระดับ | ปัญหา | หลักฐาน | การแก้ |
|---|---|---|---|---|
| F1 | สูง | ไม่มีทาง deploy คำสั่งเดียว และไม่มี preflight: ไม่ตรวจ Docker/Compose v2, `.env` ที่ยังเป็น `change-me` ใช้ได้ (และไฟล์ secret ไม่ได้จำกัดสิทธิ์), `BIND_ADDR` ที่ไม่ใช่ IP ของเครื่องทำให้ compose ล้มกลางทาง, พอร์ต 53/5300/8080 ถูกใช้อยู่ (เช่น systemd-resolved จอง 53) แล้วไม่มีใครเตือนก่อน | `Makefile` มีแค่ `up`; ไม่มีการตรวจ `.env` | `make deploy` = preflight → build → up → รอ healthy → seed → smoke; สร้าง `.env` (chmod 600) พร้อม key สุ่มเองถ้ายังไม่มี |
| F2 | สูง | `deploy/registrar/Dockerfile` ใน repo ไม่เคยถูก build ตามที่เป็น (ในเครื่อง AI ต้องเติม CA ของ proxy) และ CI ไม่ได้รัน integration เลย → ไม่มีหลักฐานว่า clone สะอาดแล้ว deploy ได้ | `.github/workflows/ci.yml` รันแค่ lint + unit | เพิ่ม job CI ที่ clone สะอาด → `make deploy` (ใช้ Dockerfile ตามจริง) → `make test-integration` → `make smoke` |
| F3 | สูง | Head-of-line blocking: ถ้า pdns ปฏิเสธ change ของโดเมนใดโดเมนหนึ่งถาวร (4xx) worker หยุดทั้ง batch และ retry ที่เดิมตลอดไป → ไม่มีโดเมนไหนถูก publish อีก | `apply_due` คืนทันทีที่ error แรก | แยกตามโดเมน: โดเมนที่ล้มข้ามไปรอบหน้า โดเมนอื่น apply ต่อ (ลำดับภายในโดเมนเดียวกันยังรักษาไว้) |
| F4 | สูง | ถ้า pdns-root เสียข้อมูล (volume หาย/สร้างใหม่) ขณะ registrar ยังรัน zone `.` จะไม่ถูกสร้างคืนจนกว่าจะ restart registrar → ทุกการ publish ล้ม 404 ไปเรื่อย ๆ | `reconciled` ตั้งเป็น True ครั้งเดียวตอนเริ่ม | publish ล้มเมื่อใด รอบถัดไปให้ reconcile ก่อน (สร้าง zone `.` + แก้ drift) |
| F5 | สูง | Web UI สร้าง `httpx.Client` ใหม่ทุก request และไม่เคยปิด → socket/file descriptor รั่วใน registrar ที่รันยาว | `client_for_key(key)` ถูกเรียกทุก request; factory ใน `api/main.py` สร้าง client ใหม่ทุกครั้ง | ใช้ HTTP client ตัวเดียวร่วมกัน (connection pool) แล้วส่ง key ราย request |
| F6 | สูง | SQLite ไม่ได้ตั้ง WAL และ busy timeout ทั้งที่มีผู้เขียนพร้อมกัน 3 ทาง (API, worker thread, `plot seed/scenario` ใน container) → `database is locked` ได้ | `db/session.py` ไม่มี `journal_mode`/`busy_timeout` | `PRAGMA journal_mode=WAL`, `busy_timeout=10000`, `synchronous=NORMAL` สำหรับไฟล์ DB |
| F7 | สูง | กับดักความปลอดภัย: RUNBOOK แนะนำ `ufw` แต่ Docker publish port ข้าม ufw (กฎ iptables ของ Docker มาก่อน) → ผู้ใช้เข้าใจผิดว่าปิดแล้ว | RUNBOOK §1.4 | แก้ RUNBOOK: ด่านจริงคือ `BIND_ADDR` + กฎใน chain `DOCKER-USER`; preflight ห้าม `0.0.0.0` |
| F8 | กลาง | ข้อมูลโตไม่หยุด: `pending_changes` ที่ apply แล้ว, `published_state` ที่เป็น `null`, `events`, และ log ของ Docker ไม่มี rotation | ไม่มีโค้ดลบ; compose ไม่มี `logging:` | ล้างแถวที่ apply แล้ว > 1 วัน, `published_state` ว่าง, events > 90 วัน ใน lifecycle job; ตั้ง log rotation 10MB×3 ทุก service |
| F9 | กลาง | จดชื่อเดียวกันพร้อมกัน 2 request → ตัวที่สองได้ 500 `INTERNAL_ERROR` แทน 409 (UNIQUE ชนตอน flush) | `register`/`create host` ไม่จับ `IntegrityError` | แปลงเป็น `DOMAIN_EXISTS`/`HOST_EXISTS` |
| F10 | กลาง | ไม่มี healthcheck ใน compose → `docker compose ps` บอก running แม้แอปพัง และ deploy รอ "พร้อมจริง" ไม่ได้ | `healthcheck` = 0 | healthcheck ให้ registrar, unbound, pdns ทุกตัว |
| F11 | กลาง | Reproducibility: image อ้างด้วย tag (tag ถูกเขียนทับได้), image unbound ติด tag `1.26.1` แต่ apt ไม่ได้ pin | compose/Dockerfile | pin base image ด้วย digest; ตั้งชื่อ image unbound ตาม base แทนเลขเวอร์ชันที่อาจไม่จริง; entrypoint log เวอร์ชันจริง |
| F12 | กลาง | `make install` ไม่ใช้ lock → dev/CI ทดสอบกับเวอร์ชันที่ต่างจาก image ได้ | `pip install -e '.[dev]'` | ติดตั้งด้วย `-c deploy/registrar/requirements.lock` |
| F13 | กลาง | ทุกครั้งที่รัน scenario (CLI/UI) สร้าง `DemoNs` (httpx client 2 ตัว) ใหม่และไม่ปิด; **ระหว่างแก้พบเพิ่ม**: `engine_from_env(api)` ไม่ใช้ `api` ที่ส่งมา → UI รัน scenario ด้วย key จาก env ไม่ใช่ key ของผู้ login | `engine_from_env` | สร้างครั้งเดียวต่อ process; ใช้ client ที่ส่งมา |
| F14 | ต่ำ | Web UI เก็บ API key ใน cookie และส่งผ่าน HTTP ธรรมดา (ไม่มี TLS) | ออกแบบตาม D-008 | ระบุชัดใน README/RUNBOOK ว่าเป็นข้อจำกัดของ dev LAN |
| F15 | ต่ำ | ถ้ามีคนเพิ่ม `--workers` ให้ uvicorn จะมี publisher หลายตัวแย่งกัน | ไม่มีคำเตือน | ระบุใน Dockerfile/RUNBOOK ว่าต้อง 1 worker |
| F16 | ต่ำ | Client ที่ไม่ได้อยู่ใน RFC1918 (เช่น VPN/Tailscale 100.64.0.0/10) ถูก unbound ปฏิเสธเงียบ ๆ | `access-control` ตายตัว | env `RESOLVER_EXTRA_ALLOW` (CIDR คั่นด้วยช่องว่าง) + เอกสาร |
| F17 | ต่ำ | backup ต้องพิมพ์คำสั่ง python ยาว ๆ เอง | RUNBOOK §6 | `make backup` / `make restore` + `make logs`, `make seed`, `make scenarios` |
| F18 | — | เรื่องที่ต้องให้ผู้ใช้ตัดสิน/ตรวจบนเครื่องจริง: A-025 (SPEC ขัดกันเรื่อง NXDOMAIN/NOT_DELEGATED), U-005 (`dig +trace` จาก LAN), Acceptance §18 บน 192.168.1.175 | PROGRESS | ทำแทนไม่ได้ — คงไว้ในรายการรอผู้ใช้ |
| F19 | สูง | (**พบตอนทดสอบ deploy**) pdns ทั้ง 3 ตัวส่ง DNS query ออกไป `secpoll.powerdns.com` ทุกครั้งที่ start (ค่าเริ่มต้นของ 4.9.17) — ขัด N8 | log `Failed to retrieve security status update for '4.9.17' on 'auth-4.9.17.security-status.secpoll.powerdns.com.'` | `security-poll-suffix=` (ว่าง) ใน `pdns.conf` ทั้งสองไฟล์ |

## ทบทวนรายงานรอบสอง

อ่านรายงานซ้ำในฐานะผู้ตรวจ: เพิ่มเรื่องสิทธิ์ไฟล์ `.env`, การตรวจเวอร์ชัน Docker/Compose และพอร์ต 5300/8080 เข้าไปใน F1 (ตอนแรกมีแค่พอร์ต 53)

ระหว่างแก้และทดสอบกรณีลบพบเพิ่ม (แก้แล้วทั้งหมด):
- ตรวจพอร์ตด้วย `ss` อย่างเดียว เครื่องที่ไม่มี `ss` ข้ามการตรวจ**เงียบ ๆ** → deploy รอ 3 นาทีแล้วล้มแบบไม่บอกสาเหตุ → เปลี่ยนเป็น probe TCP ผ่าน `/dev/tcp` (ไม่ต้องมีเครื่องมือเสริม) + UDP ผ่าน `ss`/`lsof` และเตือนเมื่อตรวจไม่ได้
- `BIND_ADDR` ที่ส่งมาตอนมี `.env` อยู่แล้วถูกเมินเงียบ ๆ → หยุดพร้อมบอกให้แก้ `.env`
- `make restore` ทำงานกับไฟล์ใน `DATA_DIR` ที่เป็นของ root จากเครื่อง host → ผู้ใช้กลุ่ม `docker` ที่ไม่ใช่ root ทำไม่ได้; และ `compose run` ชน IP คงที่ของ registrar → ทำงานไฟล์ใน container `--network none` และตรวจ `integrity_check` ก่อนหยุดระบบ
- `engine_from_env(api)` ไม่ใช้ client ที่ส่งมา (รวมไว้ใน F13)
- RUNBOOK เดิมสั่งปิด `DNSStubListener` ของ systemd-resolved เสมอ ซึ่งไม่จำเป็น (resolved ฟัง `127.0.0.53/54` ไม่ชนกับ IP ของ LAN) และแก้ `/etc/resolv.conf` ของเครื่องโดยไม่จำเป็น → ทำเฉพาะเมื่อ preflight แจ้งชน

## ผลหลังแก้

| ID | สถานะ | commit | หลักฐาน (รายละเอียดใน PROGRESS หัวข้อ Hardening) |
|---|---|---|---|
| F1 | ✅ | `P8-H01` | `make deploy` จากสถานะสะอาด → smoke 6/6; ซ้ำ 2 รอบ idempotent; กรณีลบ 6 แบบ (change-me, 0.0.0.0, IP ไม่ใช่ของเครื่อง, key สั้น, BIND_ADDR ไม่ตรง `.env`, พอร์ต 8080 ถูกใช้) → `ERROR:` ชัดเจนก่อนแตะ Docker |
| F2 | ✅ | `P8-H02` | CI run [#12](https://github.com/pishitlab/plot.cli/actions/runs/39897731045) job `integration` **success** บน `ubuntu-latest` (เครื่องสะอาด, build ด้วย Dockerfile ใน repo ตามจริง): `make deploy` 40 วิ → deploy ซ้ำ 10 วิ → `make test-integration` ผ่าน → backup/restore + smoke ผ่าน |
| F3, F4 | ✅ | `P8-H03` | unit test R-PUB-09 + reconcile หลัง publish ล้ม |
| F5, F13 | ✅ | `P8-H05` | client ตัวเดียวต่อ process, key ราย request; scenario ใช้ client ของผู้ login |
| F6 | ✅ | `P8-H06` | WAL + busy_timeout, test เขียนพร้อมกัน 3 thread |
| F7, F14, F15, F16 (เอกสาร) | ✅ | `P8-H07` | RUNBOOK §1, §5–§8, README |
| F8 | ✅ | `P8-H08`, `P8-H10` | prune ใน lifecycle job + log rotation 10MB×3 |
| F9 | ✅ | `P8-H09` | 409 แทน 500 เมื่อจดพร้อมกัน |
| F10, F11, F15, F16, F19 | ✅ | `P8-H10` | ทุก service `(healthy)`, digest pin, `RESOLVER_EXTRA_ALLOW` render แล้ว checkconf ผ่าน, secpoll ใน log = 0 |
| F12, F17 | ✅ | `P8-H01` | `make install` ด้วย lock; backup → ลบโดเมน → restore → โดเมนและ delegation กลับมา (`fixed: ['backup-test.com']`) |
| F18 | ⏸ รอผู้ใช้ | — | A-025, U-005, U-006 (ใหม่: กฎ `DOCKER-USER`), Acceptance §18 บน 192.168.1.175, tag `v1.0.0` |

ผลรวมหลังแก้ (container ของ AI, Docker 29.9.1 / Compose v5.6.0): `make lint` ผ่าน · `make test` 572 passed (coverage 99.80%, projector 100%) · `make test-integration` 26 passed

### ข้อจำกัดที่ยังเหลือ (ตั้งใจ ไม่ใช่ข้อบกพร่อง)
- ไม่มี TLS / key เดียว / ไม่มี user — ตาม SPEC (dev LAN) และระบุใน README/RUNBOOK §8
- container รันเป็น root (ไฟล์ใน `DATA_DIR` เป็นของ root) — ไม่เปลี่ยนตอนนี้เพราะจะทำให้ DATA_DIR เดิมเปิดไม่ได้; `make restore` ทำงานผ่าน container จึงไม่ต้อง sudo, ลบ `data/` ต้อง sudo (RUNBOOK §6)
- ผลทั้งหมดได้จาก container ของ AI ด้วย `BIND_ADDR=127.0.0.1` — บนเครื่องจริงต้องรัน `BIND_ADDR=192.168.1.175 make deploy` แล้วทำ Acceptance §18
