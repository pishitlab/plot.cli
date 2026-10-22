# plot.cli — Domain Sandbox

ระบบจำลองผู้รับจดทะเบียนโดเมน (registrar) + registry (zone `.` จำลอง) + DNS resolver
ให้ทีมพัฒนาระบบ hosting ทดสอบ flow "add domain → ตั้ง nameserver → ตรวจว่า NS ชี้มาหาเรา → ยืนยันความเป็นเจ้าของ"
ได้ซ้ำ ๆ โดยไม่ต้องใช้ IP จริงหรือโดเมนจริง

> ⚠️ สำหรับ dev LAN เท่านั้น ห้ามเปิดสู่อินเทอร์เน็ต

- สเปกและสถาปัตยกรรม: [`docs/SPEC.md`](docs/SPEC.md)
- สถานะงาน: [`docs/PROGRESS.md`](docs/PROGRESS.md)

## เริ่มพัฒนา

ต้องมี Python 3.12 และ `make`

```sh
make install   # สร้าง .venv และติดตั้ง package + dev tools
make lint      # ruff (lint + format check) และ mypy --strict
make test      # unit tests (ไม่รวม integration)
make fmt       # จัดรูปแบบโค้ดอัตโนมัติ
```

ค่า config ตัวอย่างอยู่ใน `.env.example` (คัดลอกเป็น `.env` แล้วแก้; ห้าม commit `.env`)
