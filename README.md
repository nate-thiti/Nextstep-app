# NextStep

> Pick Up Where You Left Off — With or Without AI.

NextStep คือ Desktop Application แบบ Local-first สำหรับบันทึก “จุดส่งต่องาน” ก่อนหยุดทำงาน เพื่อให้ผู้ใช้หรือ AI กลับมาทำต่อได้ทันที โดยไม่ต้องไล่จำว่าเคยทำอะไร หยุดอยู่ตรงไหน เปิดไฟล์ใด และควรทำอะไรต่อ

โครงการอยู่ในช่วงเริ่มต้นและยังไม่มี Production Release รายละเอียดเชิงผลิตภัณฑ์อยู่ใน [Concept (Version 2.0).md](<Concept (Version 2.0).md>), ข้อกำหนดหลักอยู่ใน [MVP_SPEC.md](MVP_SPEC.md), แนวทางหน้าจออยู่ใน [UX_SPEC.md](UX_SPEC.md) และสัญญาของ Local MCP อยู่ใน [MCP_SPEC.md](MCP_SPEC.md)

## ปัญหาที่ต้องการแก้

Todo Application ทั่วไปบอกว่า “มีงานอะไรต้องทำ” แต่เมื่อกลับมาทำงานเดิมหลังผ่านไปหลายชั่วโมงหรือหลายวัน ผู้ใช้ยังต้องเสียเวลารื้อฟื้นว่า:

- ครั้งล่าสุดทำอะไรเสร็จแล้ว
- หยุดอยู่ตรงไหน
- ติดปัญหาอะไร
- ขั้นตอนถัดไปคืออะไร
- ต้องเปิดไฟล์ โฟลเดอร์ URL หรือ Repository ใด

NextStep ให้ผู้ใช้สร้าง Work Item เพียงครั้งเดียว แล้วบันทึกความคืบหน้าลงในงานเดิมผ่าน Progress Update ระบบยังใช้ชื่อ `Checkpoint` ภายใน Data Model แต่ไม่แสดงคำเทคนิคนี้เป็น flow หลักของ UI

## วงจรการใช้งานหลัก

```text
สร้างงานครั้งเดียว → ทำงาน → Update progress → หยุด
       ↑                              ↓
       └──── Continue work เดิม ──────┘
```

ผลิตภัณฑ์ต้องทำให้การอัปเดตงานเร็วพอที่จะใช้เป็นประจำ และทำให้ Work Detail มีประโยชน์กว่าการไล่ค้นประวัติด้วยตนเอง

## ผู้ใช้กลุ่มแรก

- Software Developer ที่สลับหลายงานหรือหลาย Repository
- Technical Knowledge Worker ที่ต้องกลับเข้าสู่บริบทเดิมเป็นประจำ
- ผู้ใช้ AI หลายเครื่องมือหรือหลายบทสนทนาและต้องการส่งต่อบริบทอย่างเป็นระบบ

Data Model จะไม่ผูกกับงานพัฒนาซอฟต์แวร์ เพื่อให้ขยายสู่งานเอกสาร งานวิเคราะห์ งานวิจัย และงานประเภทอื่นได้ในอนาคต

## กลุ่มผู้ใช้ที่จะขยายในอนาคต

NextStep จะเริ่มจาก Software Developer และ Technical Knowledge Worker เพื่อพิสูจน์วงจร Checkpoint และ Resume ก่อน จากนั้นจึงขยายไปยังกลุ่มอื่นตามข้อมูลจากการใช้งานจริง

การขยายไม่ได้หมายถึงการสร้างระบบแยกสำหรับทุกอาชีพ Core Model จะยังใช้คำถามกลางชุดเดียวกัน ได้แก่ ทำอะไรเสร็จแล้ว หยุดอยู่ตรงไหน ติดอะไร ต้องทำอะไรต่อ และใช้อะไรอ้างอิง ส่วนความต้องการเฉพาะจะรองรับผ่าน Template, Reference Type, Metadata และ Integration ที่เพิ่มภายหลัง

| กลุ่มผู้ใช้ | ปัญหาและบริบทที่ต้องรักษา | ความสามารถที่อาจเพิ่ม |
| --- | --- | --- |
| นักเขียนและ Content Creator | จำไม่ได้ว่าเขียนถึงส่วนใด แนวคิดใดตัดออก โทนงานเป็นแบบใด และต้องค้นคว้าอะไรต่อ | Writing Checkpoint, Outline/Section Reference, Draft Version, แหล่งอ้างอิง และรายการประเด็นที่ต้องเขียนต่อ |
| นักวิจัยและนักศึกษา | สลับระหว่างหัวข้อ เอกสาร และการทดลองจำนวนมาก พร้อมต้องจำสมมติฐานและข้อค้นพบล่าสุด | PDF/DOI Reference, Research Note, Citation Metadata, Experiment Checkpoint และคำถามวิจัยที่ยังไม่ตอบ |
| Data Analyst และ Data Scientist | ต้องจำ Dataset, Query, Notebook, สมมติฐาน ผลลัพธ์ และข้อจำกัดของการวิเคราะห์ | Dataset/Notebook Reference, Query Snippet, Experiment Run, Result Summary และ Data-quality Blocker |
| Designer และ UX Researcher | งานกระจายอยู่ใน Design File, Prototype, Feedback และผลการวิจัยหลายรอบ | Design-file Reference, Frame/Prototype Link, Design Decision, Feedback Summary และรายการ Iteration ถัดไป |
| Product Manager | ต้องตาม Decisions, Assumptions, Stakeholder Feedback และงานที่รอทีมอื่น | Decision Log, Meeting/Spec Reference, Dependency, Owner, Follow-up และ Validation Status |
| Project Coordinator และ Operations | มีงานติดตามหลายฝ่าย ต้องจำสิ่งที่ตกลง สิ่งที่รอ และกำหนดเวลาสำคัญ | Contact/Stakeholder Reference, Waiting-for Status, Follow-up Date, Handoff Note และ Recurring Checkpoint |
| ผู้ทำงานเอกสารและงานสำนักงาน | สลับระหว่างเอกสาร แบบฟอร์ม อีเมล และขั้นตอนอนุมัติ | Document/Folder Reference, Approval State, Revision Note, Recipient และขั้นตอนดำเนินการถัดไป |
| Freelancer และผู้ทำงานหลายลูกค้า | ต้องแยกบริบท ลูกค้า ไฟล์ ขอบเขตงาน และสิ่งที่รอในหลายโปรเจกต์ | Client/Project Grouping, Scope Note, Deliverable Reference, Waiting-for-client Status และ Milestone Checkpoint |
| ผู้ใช้ทั่วไปและงานส่วนบุคคล | งานถูกพักไว้นาน ข้อมูลกระจาย และจำไม่ได้ว่าดำเนินการถึงขั้นใด | Simple Template, Reminder/Follow-up, URL/File Reference และ Resume Summary ที่ใช้ภาษาง่าย |

### หลักการขยายกลุ่มผู้ใช้

- เพิ่มกลุ่มใหม่เมื่อ Core Workflow แก้ปัญหา Checkpoint และ Resume ของกลุ่มแรกได้แล้ว
- ศึกษางานจริงของแต่ละกลุ่มก่อนเพิ่มฟิลด์หรือ Integration
- ใช้ Template และ Optional Metadata ก่อนเปลี่ยน Core Schema
- ไม่แสดงฟิลด์เฉพาะอาชีพให้ผู้ใช้ทุกคนเห็นโดยไม่จำเป็น
- หลีกเลี่ยงการเปลี่ยน NextStep ให้เป็น Project Management Suite หรือเครื่องมือเฉพาะทางของทุกอาชีพ
- ให้ผู้ใช้สร้างหรือปรับ Template เองได้ในอนาคต เพื่อลดการสร้างฟีเจอร์แยกสำหรับทุกกรณี

## ขอบเขต MVP

### ฟีเจอร์หลัก

- สร้าง แก้ไข ค้นหา และเปลี่ยนสถานะ Work Item
- อัปเดตความคืบหน้าและสถานะภายใน Work Item เดิม
- แสดง Work Detail จาก Progress Update ล่าสุด
- แสดง Progress History แบบ Timeline
- เชื่อมโยงไฟล์ โฟลเดอร์ URL และ Git Repository
- จัดกลุ่มงานแบบไม่บังคับ
- สำรองและส่งออกข้อมูล Local
- เปิด Local MCP Server แบบ Read-only
- ให้สิทธิ์ MCP Write Tools ทีละ capability พร้อม Audit Log

### ยังไม่อยู่ใน MVP

- Cloud Sync
- Login และระบบบัญชีผู้ใช้
- Remote MCP
- การลบ Work Item ผ่าน MCP
- Permission Policy แบบหลายผู้ใช้
- Dashboard และรายงานเชิงสถิติ
- AI-generated Summary แบบอัตโนมัติ
- Cross-AI Automation

## Tech Stack ที่เสนอ

Tech Stack ส่วนนี้เป็นแนวทางเริ่มต้น ยังปรับได้เมื่อมี Prototype และข้อมูลจากการใช้งานจริง

| ส่วน | เทคโนโลยี | เหตุผล |
| --- | --- | --- |
| Language | Python 3.12+ | ใช้ร่วมกันได้ทั้ง Desktop, Core Services และ MCP Server |
| Desktop UI | PySide6 | Native desktop UI ผ่าน Qt และรองรับหลายระบบปฏิบัติการ |
| Local Database | SQLite | ไม่ต้องติดตั้ง Server, ทำงาน Offline และ Backup ง่าย |
| ORM / Data Access | SQLAlchemy 2.x | แยก Data Access ออกจาก UI และรองรับ Transaction ชัดเจน |
| Database Migration | Alembic | เปลี่ยน Schema ได้อย่างมีลำดับเมื่อแอปถูกติดตั้งไปแล้ว |
| Validation | Pydantic 2.x | ตรวจ Structured Context ที่ใช้ร่วมกันระหว่าง UI, Services และ MCP |
| MCP | Official MCP Python SDK | สร้าง Local MCP Server พร้อม Read และ Write Tools |
| Testing | pytest | ทดสอบ Core Services, Database และ MCP Tools |
| Lint / Format | Ruff | รวม Lint และ Format โดยตั้งค่าไม่ซับซ้อน |
| Type Checking | mypy หรือ Pyright | ตรวจขอบเขตของ Service Layer และ Data Model ก่อน Runtime |
| Dependency Management | uv | จัดการ Python, Virtual Environment, Dependencies และ Lockfile |
| Packaging | PyInstaller หรือ Nuitka | ตัวเลือกสำหรับสร้าง Desktop Executable; จะเลือกหลังทดสอบ Prototype |

ไม่ควรให้ Desktop UI หรือ MCP Tools เข้าถึงฐานข้อมูลโดยตรง ทั้งสองทางต้องเรียกผ่าน Core Services เพื่อให้ Validation, Transaction และกฎของระบบอยู่ในจุดเดียว

## สถาปัตยกรรมเบื้องต้น

```text
           Desktop UI                AI Clients
             PySide6               MCP-compatible
                |                         |
                |                         v
                |                  Local MCP Server
                |                         |
                └──────────┬──────────────┘
                           v
                 Shared Core Services
             Work · Checkpoint · Context
                 References · Validation
                           |
                           v
                    SQLite Database
                  Local-first Storage
```

Desktop UI และ MCP Server ทำงานแยก Process แต่ใช้ Core Services และฐานข้อมูลเดียวกัน

ข้อกำหนดของ SQLite:

- เปิด WAL mode
- กำหนด Busy Timeout
- ใช้ Transaction สำหรับการเขียนข้อมูล
- ใช้ UUID เป็น Primary Identifier
- บันทึกเวลาเป็น UTC และแปลงเป็นเวลาท้องถิ่นตอนแสดงผล
- เตรียม `created_at` และ `updated_at` ให้กับข้อมูลหลัก

## Data Model เบื้องต้น

| Table | หน้าที่ |
| --- | --- |
| `work_items` | เก็บงาน เป้าหมาย สถานะ และข้อมูลการจัดกลุ่ม |
| `checkpoints` | เก็บบริบทและประวัติ ณ จุดหยุดงาน |
| `work_references` | เก็บ Reference ของไฟล์ โฟลเดอร์ URL และ Repository |
| `app_settings` | เก็บการตั้งค่า Local รวมถึงสถานะ ขอบเขต MCP และ Write capability |
| `audit_logs` | เก็บ metadata ของ MCP write attempt โดยไม่เก็บเนื้องาน |

Structured Fields หลักของ Checkpoint:

- `completed_work`
- `stopped_at`
- `blockers`
- `next_actions`
- `context_summary` (ไม่บังคับ)
- `created_at`

Schema จริงจะถูกกำหนดระหว่าง Phase 1 และจัดการการเปลี่ยนแปลงผ่าน Migration

## MCP

Local MCP Server ใช้ stdio และมี Tools สองกลุ่ม

Read tools:

- `list_work_items`
- `get_work_context`
- `get_latest_checkpoint`
- `search_checkpoints`

Write tools (ปิดเป็นค่าเริ่มต้นและเปิดทีละ capability):

- `create_work_item`
- `update_work_item`
- `save_progress_update`
- `change_work_item_status`
- `add_reference`
- `update_reference`
- `delete_reference`

ระดับการเปิดเผยข้อมูลสำหรับการอ่าน:

1. ปิด MCP
2. อนุญาตเฉพาะ Work Item ที่ผู้ใช้เลือก
3. อนุญาตทุก Work Item

การเขียนต้องเปิด **Allow MCP to change data** และติ๊ก capability ที่ต้องการ ทุกครั้งที่พยายามเขียนจะถูกบันทึกใน Audit Log เฉพาะชื่อ tool, ผลลัพธ์, ID และชื่อ field ที่เปลี่ยน โดยไม่เก็บชื่อ เป้าหมาย ข้อความ Progress หรือ URL การลบ Work Item ถาวรยังทำได้จาก Desktop เท่านั้น

### เชื่อมต่อ Local MCP ระหว่างพัฒนา

1. เปิด Settings → AI access (MCP)
2. เลือก Selected work items หรือ All work items
3. ถ้าต้องการให้ AI แก้ข้อมูล ให้เปิด Allow MCP to change data และติ๊ก capability
4. ตั้ง MCP client ให้รัน `.venv\Scripts\nextstep-mcp.exe` ผ่าน stdio

ตัวอย่าง configuration และ Input/Output contract อยู่ใน [MCP_SPEC.md](MCP_SPEC.md)

## โครงสร้างโปรเจกต์ที่เสนอ

```text
NextStep-App/
├── src/
│   └── nextstep/
│       ├── application/      # Use cases และ Core Services
│       ├── domain/           # Entities, Value Objects และกฎของระบบ
│       ├── infrastructure/   # SQLite, SQLAlchemy, Filesystem และ Configuration
│       ├── desktop/          # PySide6 UI
│       ├── migrations/       # Alembic resources ที่ติดไปกับ Wheel
│       └── mcp_server/       # MCP Server และ Tool adapters
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
├── pyproject.toml
├── README.md
└── LICENSE
```

โครงสร้างนี้เป็นเป้าหมาย ไม่จำเป็นต้องสร้างทุกโฟลเดอร์ตั้งแต่วันแรก ให้เพิ่มเมื่อมีโค้ดที่รับผิดชอบส่วนนั้นจริง

## Development Roadmap

| Phase | งานหลัก | สิ่งที่ต้องพิสูจน์ |
| --- | --- | --- |
| 1 | SQLite, Core Services, Work Items, Checkpoints | Data Model รองรับวงจรงานหลัก |
| 2 | Update Progress และ Work Detail | อัปเดตงานเดิมง่ายและกลับมาทำต่อได้จริง |
| 3 | References, Search, History, Backup และ Export | บริบท Local เพียงพอสำหรับการใช้งานจริง |
| 4 | Local MCP Server แบบ Read-only | AI ใช้บริบทเพื่อช่วยทำงานต่อได้ |
| 5 | ปรับ UX และ Data Model จากการทดลองใช้ | ขั้นตอนและฟิลด์ตรงกับพฤติกรรมผู้ใช้ |
| 6 | MCP Write Tools, Permissions และ Audit Logs | AI อัปเดตข้อมูลได้อย่างควบคุมและตรวจสอบได้ |
| 7 | AI Handoff และ Context Summary | ส่งต่องานข้าม AI โดยไม่ผูกกับผู้ให้บริการรายเดียว |

## หลักการพัฒนา

- **Resume-first:** ให้ความสำคัญกับการกลับมาทำงานต่อมากกว่าการนับจำนวนงาน
- **Low-friction Capture:** การสร้าง Checkpoint ต้องเร็วและไม่เป็นภาระ
- **Local-first:** ฟีเจอร์หลักทำงานได้โดยไม่เชื่อมต่ออินเทอร์เน็ต
- **No Login Required:** รุ่น Local ใช้งานได้โดยไม่ต้องมีบัญชี
- **AI-optional:** ไม่เชื่อม AI ก็ใช้งานฟีเจอร์หลักได้ครบ
- **Privacy by Design:** ข้อมูลไม่ออกจากเครื่องโดยอัตโนมัติ
- **Focused First:** ทำประสบการณ์ของกลุ่มแรกให้ดีก่อนขยายขอบเขต
- **Incremental Development:** แต่ละ Phase ต้องมีสิ่งที่ทดลองใช้และตรวจสอบได้
- **Open Source Friendly:** ระบบต้องติดตั้ง ตรวจสอบ และใช้งาน Local ได้โดยไม่พึ่งบริการส่วนกลาง

## การเริ่มพัฒนา

Phase 1–6 ถูกสร้างแล้ว: Sidebar ใช้สำหรับ Navigation, Status เป็น Filter/Action ของ Work, Progress Update ไม่เปลี่ยนสถานะงาน และ MCP มี Read/Write Tools พร้อม Permission และ Audit Log

### สิ่งที่ต้องมี

- Windows 10/11 64-bit
- [uv](https://docs.astral.sh/uv/) — จัดการ Python 3.12 ตาม `.python-version` ให้อัตโนมัติ

### คำสั่งที่ใช้บ่อย

```powershell
uv sync                     # ติดตั้ง dependency และสร้าง .venv
uv run nextstep             # เปิดแอป Desktop
uv run pytest               # รัน test ทั้งหมด
uv run ruff check .         # ตรวจ lint
uv run ruff format .        # จัดรูปแบบโค้ด
uv run pyright              # ตรวจ type
```

> ถ้า `uv` ยังไม่อยู่ใน `PATH` ให้ใช้ `python -m uv ...` แทนทุกคำสั่ง

### การเปิดแอป

แอปจะสร้างฐานข้อมูล, backup และ log ใต้ `%LOCALAPPDATA%\NextStep` โดยอัตโนมัติ สำหรับ development ให้กำหนด `NEXTSTEP_DATA_DIR` เพื่อไม่แตะข้อมูลจริง

```powershell
$env:NEXTSTEP_DATA_DIR = "$PWD\.localdata"
uv run nextstep
```

ถ้า Schema เปลี่ยนแปลงและต้อง Migration ระบบจะสำรองฐานข้อมูลเดิมไปที่ `backups\pre-migration-<timestamp>.db` ก่อนทุกครั้ง

### Backup, Restore และ Export

ทำได้จากหน้า **Settings** ภายในแอป:

- **Back up…** สร้างไฟล์ `.zip` ที่มี SQLite snapshot และ `manifest.json` (เวอร์ชันแอป, schema, จำนวนข้อมูล) โดยไม่คัดลอกไฟล์ที่ References ชี้ไป
- **Restore…** ตรวจ manifest และ schema พร้อมความสมบูรณ์ของฐานข้อมูลก่อน จากนั้นสำรองข้อมูลปัจจุบันเป็น `backups\pre-restore-<timestamp>.zip` แล้วจึงแทนที่ และปิดแอปเพื่อให้เปิดใหม่ด้วยข้อมูลที่ Restore
- **Export JSON…** ส่งออก Work Items, Checkpoints และ References เป็น UTF-8 JSON พร้อม `export_version` และ `exported_at`

### ฐานข้อมูลระหว่างพัฒนา

```powershell
$env:NEXTSTEP_DATA_DIR = "$PWD\.localdata"
uv run alembic upgrade head
```

### ชั้นของระบบที่สร้างแล้ว

```text
src/nextstep/
├── domain/           # Entities, enums, validation rules (ไม่พึ่ง SQLAlchemy หรือ UI)
├── application/      # Use cases, DTOs, repository ports, Resume/Settings/Portability
├── infrastructure/   # SQLite engine, repositories, migrations, archive, paths, OS adapter, logging
├── desktop/          # PySide6 UI: Work List, Work Detail, Progress History, Settings, dialogs
└── main.py           # Entry point (`uv run nextstep`)
migrations/           # Alembic migration
tests/
├── unit/             # Validation และ formatting helpers
├── integration/      # รันกับ SQLite จริงและ Migration จริง
└── ui/               # Headless UI tests ด้วย pytest-qt
```

### ลำดับงานถัดไป

1. Search ด้วย SQLite FTS5 พร้อม `LIKE` fallback (Phase 3)
2. ทดลองใช้ MCP Write Tools กับ client จริงและเก็บปัญหาด้าน setup/compatibility
3. ประเมิน Packaging ด้วย PyInstaller (Phase 3)
4. ออกแบบ AI Handoff และ Context Summary (Phase 7)

## สถานะโครงการ

**สถานะ:** Phase 6 (MCP write tools, permissions และ audit logs) — MCP เขียนข้อมูลได้เมื่อผู้ใช้ให้สิทธิ์ทีละ capability และทุกการเปลี่ยนแปลงถูกบันทึกใน Audit Log

ความสามารถที่มีตอนนี้:

- Work List พร้อมตัวกรองสถานะ/กลุ่ม, ค้นหา, ตัวชี้ว่ามี Blocker และ Load More ทุก 100 รายการ
- Work List สลับ Focus view (ตารางพร้อม Preview) และ Compact view ได้ พร้อมจำค่าที่เลือก
- Update Progress (`Ctrl+Enter` เพื่อบันทึก) พร้อม Inline Validation
- เปลี่ยนสถานะด้วย Pause, Resume, Finish และ Archive แยกจาก Progress Update
- Permanent Delete ที่ต้องพิมพ์ชื่องานยืนยัน
- Work Detail ที่แสดง Goal, Next Action, Current Stopping Point, Blockers, Progress และ References
- Copy Handoff จาก Work Detail เป็น Markdown พร้อมบริบทล่าสุดและ References
- Back navigation ที่รักษา Search, Filter และ Selection เดิม
- Progress Timeline ใน Work Detail แสดง 5 Updates ล่าสุด โดยมีหน้าประวัติเต็มสำหรับแก้ไขและลบ
- Progress History แบบ Timeline (แก้ไข/ลบได้)
- References สำหรับไฟล์ โฟลเดอร์ URL และ Git Repository พร้อมเปิดผ่าน OS
- Backup เป็น `.zip` พร้อม manifest, Restore พร้อม Pre-restore Backup และ JSON Export
- Restore ตรวจ Alembic revision จากฐานข้อมูลจริง และยืนยัน Reference ที่มาจาก Backup แยกทีละรายการ
- Local MCP Server แบบ stdio พร้อม 4 read tools
- Settings มี AI client setup guide สำหรับ Codex, Claude, Cursor, VS Code/Copilot, Gemini CLI, Windsurf และ Generic stdio พร้อม config ที่ใช้ executable path จริง
- MCP Write Tools 7 รายการ: สร้าง/แก้ Work Item, บันทึก Progress Update, เปลี่ยนสถานะ, เพิ่ม/แก้/ลบ Reference
- สิทธิ์ MCP แยก Read scope (Off/Selected/All) และ Write capability ทีละ operation ปิดเป็นค่าเริ่มต้น
- Audit Log แบบไม่เก็บเนื้องาน พร้อมมุมมอง MCP activity ล่าสุดใน Settings
- Light/Dark/System theme ที่จำค่าไว้ในเครื่อง
- Keyboard shortcuts: `Ctrl+N` (งานใหม่), `Ctrl+F` (ค้นหา), `Ctrl+Shift+U` (Update Progress), `Esc` (ย้อนกลับหรือปิดฟอร์ม)
- Quick Capture จาก Sidebar หรือ `Ctrl+Alt+U` เพื่อเลือกงานและบันทึก Progress โดยไม่ต้องเปิด Work Detail
- Handoff Preview แบบ Short/Full ก่อนคัดลอก, Pin Work, Follow-up Reminder และ Command Palette (`Ctrl+K`)
- Command Palette ครอบคลุม Navigation, Work lifecycle, Progress, Handoff, References, View, Filter, Theme, Backup, Restore, Export และ MCP activity

ยังไม่มี Release, Package หรือ Installer ส่วน Local MCP Server พร้อมใช้งานสำหรับการรันจาก Development Environment

## Open Source และ License

โครงการตั้งใจพัฒนาแบบ Open Source แต่ยังไม่ได้เลือก License อย่างเป็นทางการ ก่อนเปิด Repository สู่สาธารณะต้องเลือก License ให้ชัดเจน เช่น:

- **MIT:** เงื่อนไขน้อย เหมาะกับการนำไปใช้และต่อยอดกว้าง
- **Apache-2.0:** คล้าย MIT แต่มีข้อกำหนดเรื่องสิทธิบัตรชัดกว่า
- **GPL-3.0:** บังคับให้งานดัดแปลงที่แจกจ่ายต่อเปิด Source ภายใต้เงื่อนไขเดียวกัน

จนกว่าจะมีไฟล์ `LICENSE` โค้ดยังไม่ได้รับอนุญาตให้นำไปใช้ ดัดแปลง หรือแจกจ่ายต่อโดยอัตโนมัติ แม้ Source Code จะมองเห็นได้

## Contributing

แนวทางการ Contribute, Coding Convention, Branch Strategy และ Pull Request Process จะเพิ่มเมื่อโครงสร้างโปรเจกต์และ Workflow แรกพร้อมใช้งาน
