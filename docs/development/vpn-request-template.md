# BelVPN / ДИТ — запрос доступа к TEST (шаблон)

**Audience:** Исполнитель (PM / lead) preparing the bank service-desk ticket  
**Purpose:** Checklist + fill-in template for **BelVPN** and **TEST server access**. Companion to the VM hardware request ([`infra/test/server-requirements.md`](../../infra/test/server-requirements.md)).  
**Contract:** № 14-03/2026 · ОАО «АСБ Беларусбанк» · VII.3 / Прил.1  
**SLA:** TEST VM — **T+28** рабочих дней от подписания договора; BelVPN historically **T+21** — подавать **раньше или вместе** с заявкой на ВМ, чтобы доступ был готов к handoff.

> **Do not execute external actions.** This file is a template only. Do **not** auto-submit to ДИТ / ЦКБ / service desk. A human copies the filled fields into the bank ticket system and attaches the bank’s official BelVPN form.

---

## 0. Before you open a ticket

- [ ] Contract signature date known → compute **T+28** calendar deadline for VM
- [ ] BelVPN target date set (aim ≤ T+21 / before VM ready)
- [ ] Hardware request drafted or attached: [`infra/test/server-requirements.md`](../../infra/test/server-requirements.md) §§1–7
- [ ] List of Исполнитель employees who need access (see §3) reviewed by PM
- [ ] Bank BelVPN / ЦКБ paper form obtained (official blank — not this markdown)
- [ ] Customer ДИТ owner / ticket queue known
- [ ] Scope confirmed: **TEST only** (not PROD)

| Planning field | Value |
| --- | --- |
| Contract signed (date) | _______________ |
| T+28 VM deadline | _______________ |
| BelVPN needed by | _______________ |
| Proposed hostname / FQDN | `ai-hub-test` / `ai-hub-test.bank.local` · _TBD_ |
| Related tickets | Bitrix TEST T+30 · Oktell TEST T+45 · KUMA |

---

## 1. DIT ticket header (copy into service desk)

| Field | Fill |
| --- | --- |
| **Request title** | AI Hub / Суфлёр — BelVPN + доступ к TEST VM (VII.3), T+28 |
| **Request type** | ☐ BelVPN only ☐ Server/OS accounts only ☐ **Both** (recommended) |
| **Environment** | **TEST** (not PROD) |
| **Requester (Исполнитель)** | ООО «ГС Ритейл» · contact: _______________ · email: _______________ · phone: _______________ |
| **Customer owner (ДИТ)** | _______________ |
| **Approver (ЦКБ / ИБ)** | _______________ (BelVPN) |
| **Needed by** | BelVPN: _______________ · VM access: **T+28** _______________ |
| **Related ticket / VM request** | #_______ / link to hardware request |
| **Justification** | Remote work of vendor engineers on bank-hosted TEST for joint acceptance (SUF-T / CHAT-T / INT-T), deploy, and support per contract VII.3 |

**Short description (paste):**

```text
Просим организовать удалённый доступ Исполнителя к тестовому контуру AI Hub / Суфлёр:
1) BelVPN для указанных сотрудников (форма ЦКБ во вложении);
2) Учётки ОС/AD и права на TEST VM (SSH, Docker) после выдачи ВМ по заявке T+28.

Контур: только TEST. PROD не требуется.
Договор № 14-03/2026. Срок ВМ: T+28 раб. дней от подписания.
```

---

## 2. What to request (two layers)

Access is **two separate grants**. Tick both on the ticket when possible.

### 2.1 BelVPN (ЦКБ / remote access)

| Item | Request |
| --- | --- |
| Product | **BelVPN** (bank remote access client) |
| Users | Employees in §3 |
| Destination | TEST segment and/or agreed **jump host** only |
| MFA | Per bank BelVPN package |
| Split-tunnel / Internet | **No** general Internet for model/`pip` downloads from VPN |
| Duration | Until end of TEST acceptance / per bank policy · renew: _______________ |

- [ ] Official BelVPN form filled (ФИО, документ, email, phone per bank rules)
- [ ] Form signed / approved internally before send
- [ ] Attached to DIT/ЦКБ ticket

### 2.2 Server access on TEST VM (ДИТ — after or with VM)

| Item | Request |
| --- | --- |
| Host | Proposed: `ai-hub-test` / FQDN _______________ |
| Accounts | Individual OS and/or AD accounts for each engineer in §3 |
| Shell | SSH (preferred) · RDP only if bank policy requires |
| Groups | Membership in group that can run **Docker** / `docker compose` (or equivalent sudo limited to Compose) |
| Home / deploy path | e.g. `/opt/sufler` readable/writable by deploy user |
| Sudo | ☐ full sudo ☐ limited (Docker + systemctl for stack) ☐ none — _agree with ДИТ_ |
| Secrets | No shared root password in ticket; vault / ДИТ handoff process |

- [ ] Accounts named in ticket (or “create per attached list”)
- [ ] Docker Engine 24+ / Compose v2 already on VM **or** requested as install step
- [ ] Jump-host path documented if direct SSH to VM is denied

---

## 3. Employee access list (attachment)

Copy rows as needed. Do **not** commit passport scans to git — attach only in the bank ticket.

| # | ФИО | Role | Corporate email | Phone | BelVPN | VM/SSH login | Doc ID (bank form) |
| ---: | --- | --- | --- | --- | :---: | --- | --- |
| 1 | | e.g. lead / devops | | | ☐ | | _per ЦКБ form_ |
| 2 | | | | | ☐ | | |
| 3 | | | | | ☐ | | |
| 4 | | | | | ☐ | | |

- [ ] Only staff who need TEST access listed (least privilege)
- [ ] Leavers removed / ticket update process agreed

---

## 4. Network scope (for firewall / VPN ACL)

Align with [`infra/test/server-requirements.md`](../../infra/test/server-requirements.md) §4. Ask ДИТ to allow **from BelVPN/jump → TEST VM**:

| From | To | Proto / port | Purpose |
| --- | --- | --- | --- |
| BelVPN / jump | TEST VM | TCP **22** (SSH) | Deploy, logs, `deploy.sh` |
| BelVPN / jump | TEST UI/API | TCP **443** (HTTPS) | Browser smoke, `/health/`, `/metrics/` |
| BelVPN / jump | TEST HTTP | TCP **80** | Optional (expect 301 → HTTPS) |
| Vendor laptop | BelVPN concentrator | per ЦКБ | Tunnel only |

**Do not request** from vendor laptops: public Postgres `:5432`, Redis `:6379`, MinIO `:9000` — internal VLAN only.

Integrations (AD / Bitrix / Oktell / KUMA) are **VM ↔ bank systems**, not BelVPN clients — covered by the VM network ticket.

- [ ] ACL text included in ticket or referenced to server-requirements §4
- [ ] PROD networks explicitly **out of scope**

---

## 5. Step-by-step (human process — do not automate)

### A. Prepare (Исполнитель)

1. Fill §1 header and §3 employee list.  
2. Complete bank BelVPN form (ЦКБ blank).  
3. Attach or cross-link VM hardware request ([`server-requirements.md`](../../infra/test/server-requirements.md)).  
4. PM review → internal approve.

### B. Submit (human only)

5. Create **one** DIT ticket (or two linked: BelVPN + VM/accounts) in the **bank** service desk.  
6. Attach forms; set due dates (BelVPN early, VM T+28).  
7. **Do not** use scripts, email bots, or CI to submit.

### C. While waiting

8. Track ticket IDs: BelVPN #_______ · VM #_______ · Accounts #_______  
9. If BelVPN slips past VM ready date → agree temporary on-site / supervised jump ([server-requirements §6](../../infra/test/server-requirements.md)).

### D. After grant — verify access

10. Install BelVPN client per bank package; MFA works.  
11. Connect → reach jump or VM (`ping`/`ssh` per policy).  
12. SSH login with issued account; `docker compose version` (or agreed check).  
13. Confirm HTTPS: `curl -kf https://<fqdn>/health/` (or via jump).  
14. Record handoff in project tracker; proceed to deploy runbook: [`docs/runbooks/deploy-test.md`](../runbooks/deploy-test.md).

| Verify | Pass? |
| --- | :---: |
| BelVPN connects | ☐ |
| Jump / VM reachable | ☐ |
| SSH works (named account) | ☐ |
| Docker rights OK | ☐ |
| HTTPS `/health/` reachable | ☐ |

---

## 6. Acceptance checklist (ДИТ ↔ Исполнитель)

| # | Check | Owner | Done |
| --- | --- | --- | :---: |
| 1 | BelVPN accounts issued for §3 list | ЦКБ / ДИТ | ☐ |
| 2 | VPN clients reach TEST jump/VM only | ЦКБ / ДИТ | ☐ |
| 3 | OS/AD accounts + Docker (or agreed) on TEST VM | ДИТ | ☐ |
| 4 | Firewall §4 applied | ДИТ | ☐ |
| 5 | Исполнитель verified SSH + `deploy.sh config` | Исполнитель | ☐ |
| 6 | No PROD access granted by mistake | ЦКБ / ДИТ | ☐ |

---

## 7. Common delays / FAQ

| Issue | Mitigation |
| --- | --- |
| BelVPN after T+28 VM idle | Escalate ЦКБ; request temporary on-site/jump |
| Shared “team” OS login only | Ask for named accounts (audit) |
| SSH blocked, RDP only | Follow bank policy; document in deploy notes |
| No Docker group | Limited sudo or ДИТ installs stack — agree in ticket |
| Vendor needs registry pull | Internal registry credentials via vault — not BelVPN Internet |
| Employee leaves | Ticket to revoke BelVPN + VM account same day |

---

## 8. Attachments checklist

- [ ] This template filled (PDF/export or paste into ticket)  
- [ ] Official **BelVPN / ЦКБ** form  
- [ ] [`infra/test/server-requirements.md`](../../infra/test/server-requirements.md) (hardware + network)  
- [ ] Employee list (§3) without storing ID scans in git  
- [ ] Optional: org chart / NDA refs per bank policy  

---

## Related

| Doc | Role |
| --- | --- |
| [`infra/test/server-requirements.md`](../../infra/test/server-requirements.md) | DIT **VM** ticket (CPU/RAM/disk/OS) + BelVPN §6 |
| [`docs/technical/server-requirements.md`](../technical/server-requirements.md) | Full DEV/TEST/PROD engineering spec |
| [`docs/runbooks/deploy-test.md`](../runbooks/deploy-test.md) | Deploy after access works |
| [`docs/development/code-review-checklist.md`](code-review-checklist.md) | Dev process (unrelated to DIT send) |

**Document owner:** Исполнитель · **Consumer:** ДИТ / ЦКБ · **Action:** human submit only — no auto-send.
