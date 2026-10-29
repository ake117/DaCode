---
title: "Google Harness² — Recursive Agent Harnessing for an Open World"
source: "https://github.com/google-research/harness2"
author: "Google Research"
created: 2026-10-18
updated: 2026-10-24
update_history:
  - "2026-10-24: เพิ่ม cross-link ไปยัง note เปรียบเทียบกับ DeepSeek Harness (DSH)"
  - "2026-10-18: สร้าง note — สรุปงานวิจัยและเฟรมเวิร์ก Harness² จาก Google Research (arXiv:2610.14224)"
tags:
  - ai/agent
  - devtools
  - research
  - self-improving-agents
type: research
status: reference
aliases:
  - Harness2
  - Harness²
  - Google Harness2
---

# Google Harness² — Recursive Agent Harnessing for an Open World

> [!abstract] สรุปสั้น
> เฟรมเวิร์ก open-source จาก **Google Research** (ต.ค. 2026, arXiv:2610.14224) สำหรับการทำ **Recursive Agent Harnessing** ในโลกกว้าง · แก้ปัญหาเดิมที่เวลา AI ทำงานพลาด เราต้องแก้ prompt มือ โดยให้ Agent **ปรับแต่งระบบรอบตัวมันเอง (Harness: prompts, tools, memory, skills) แบบวนซ้ำ (Recursive)** โดยไม่ต้องแก้ Model Weights · ผลทดสอบช่วยเพิ่มคะแนนบน benchmark (WorkBuddy-Bench, JobBench, LAB) สูงขึ้น 4.5 ถึง 11.8 จุด

---

## ⚙️ แนวคิดหลัก (Core Concepts)

*Harness* คือระบบรอบตัวโมเดลที่ทำให้มันกลายเป็น Agent (เช่น prompt, เครื่องมือ, หน่วยความจำ, ทักษะ, การจัดลำดับ) ส่วน **Harnessing** คือกระบวนการปรับแต่งและ optimize ระบบนั้น

Harness² เชื่อมโยง **2 ระดับของการวนซ้ำ (Two Levels of Recursion):**

1. **Task-level recursion (Propose–Probe–Compose):**
   - เมื่อ Agent เจอโจทย์เฉพาะหน้า ใช้ขั้นตอนวนซ้ำแบบ Contrastive:
     - **Propose:** เสนอการแก้ไข harness (เช่น ปรับ prompt, เพิ่มเครื่องมือ/skill) สำหรับงานนี้
     - **Probe:** ทดลองรันและตรวจสอบผลกระทบจากการเปลี่ยนแปลงนั้นในงานจริง
     - **Compose:** สังเคราะห์และรวมร่างเป็น harness ที่สมบูรณ์ที่สุดจากผลลัพธ์ที่เปรียบเทียบกัน โดยไม่ต้องอาศัยเฉลย (zero ground-truth feedback)
2. **Harnessing-level recursion:**
   - นำบทเรียนและ harness ที่สำเร็จจากงานระดับ Task ไปอัปเดตใส่ไว้ใน **persistent improvement harness** (หน่วยความจำ/ทักษะถาวร) เพื่อให้การทำงานในอนาคตฉลาดและแม่นยำขึ้นเรื่อย ๆ

---

## 📊 ผลการทดสอบ (Benchmark Results)

- ทดสอบบน 3 professional benchmarks และ 4 model–harness configurations (รวมถึง GLM-5 และ Gemini 3.5 Flash)
- เพียงแค่ 1 ขั้นตอนของ Harness² ช่วยยกระดับประสิทธิภาพ:
  - **WorkBuddy-Bench:** +11.5 จุด
  - **JobBench:** +4.5 จุด
  - **LAB (partial pass rate):** +11.8 เปอร์เซ็นต์
- หากเพิ่มงบประมาณการวนซ้ำ (task-level recursion budget) จะยิ่งได้ผลลัพธ์ที่ดีขึ้น

---

## 💡 นัยต่อการพัฒนา Agent (มุมมองแคลร์)

- **อนาคตของ AI Agents:** ก้าวข้ามยุค "Static Prompting" สู่ยุค **Self-Evolving Agents** ที่ Agent สามารถปรับแต่งเครื่องมือและทักษะรอบตัวเพื่อแก้โจทย์แปลกใหม่ได้เองหน้างาน (Test-time compute optimization)
- **การประยุกต์ใช้:** แนวคิด Propose-Probe-Compose สามารถนำไปประยุกต์เขียน Auto-loop ให้กับ coding agents ต่าง ๆ (เช่น Pi coding agent หรือ Hermes เอง) เพื่อให้ระบบแก้บั๊กและเรียนรู้จากความผิดพลาดได้อัตโนมัติ

---

## 🔗 Related

- [[Google Harness2 vs DeepSeek Harness (DSH) — เปรียบเทียบ]] — เทียบระเบียบวิธี Harness² กับ runtime dsh (คนละชั้นสถาปัตยกรรม)
- [[REA - Reverse Engineer Anything (MCP)]] — เครื่องมือและแนวคิด Agentic Tooling
- [[HyperFrames - Write HTML Render Video]] — ตัวอย่าง Agent-driven workflow อีกรูปแบบ
- [[mattpocock-skill-vps]] — ชุด Skills และการจัดการความรู้ของ Agent

## 📚 Sources

- GitHub: https://github.com/google-research/harness2 (Google Research, ต.ค. 2026)
- Paper: arXiv:2610.14224 — *Recursive Agent Harnessing for an Open World*
- Website: https://harness2.github.io/
