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

## ทบทวนรายงานรอบสอง

อ่านรายงานซ้ำในฐานะผู้ตรวจ: เพิ่มเรื่องสิทธิ์ไฟล์ `.env`, การตรวจเวอร์ชัน Docker/Compose และพอร์ต 5300/8080 เข้าไปใน F1 (ตอนแรกมีแค่พอร์ต 53)

## ผลหลังแก้

_(เติมหลังแก้ครบ — ดูหัวข้อถัดไป)_
