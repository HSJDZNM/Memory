# 06_授权与访问控制

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：授权模型与访问控制实现：通用授权、IDOR、事务授权、多租户隔离，以及授权的自动化测试与回归测试。

**文档数**：6

- [Authorization Cheat Sheet](Authorization_Cheat_Sheet.md)
  - `ASVS V8.1 V8.2 V8.4 V16.3: · Top10 A01 · MASVS MASVS-AUTH`
  - Authorization may be defined as "the process of verifying that a requested action or service is approved for a specific entity" (NIST). Authorization is distinct from authentication which is the proce…

- [Authorization Regression Testing Cheat Sheet](Authorization_Regression_Testing_Cheat_Sheet.md)
  - `—`
  - Authorization implementation is rarely static. As applications evolve, new API endpoints are added, data layers are refactored, and microservices are decoupled. While initial security testing might va…

- [Authorization Testing Automation Cheat Sheet](Authorization_Testing_Automation_Cheat_Sheet.md)
  - `ASVS V8.1 · PC C7`
  - To deal with this problem, we recommend that developers automate the evaluation of the authorizations and perform a test when a new release is created. This ensures that the team knows if changes to t…

- [Insecure Direct Object Reference Prevention Cheat Sheet](Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.md)
  - `ASVS V8.2 · PC C7 · Top10 A01 · MASVS MASVS-CODE`
  - Insecure Direct Object Reference (IDOR) is a vulnerability that arises when attackers can access or modify objects by manipulating identifiers used in a web application's URLs or parameters. It occurs…

- [Multi-Tenant Application Security Cheat Sheet](Multi_Tenant_Security_Cheat_Sheet.md)
  - `ASVS V8.4`
  - Multi-tenant applications serve multiple customers (tenants) from a shared infrastructure, codebase, and often shared databases. This architecture is the foundation of modern SaaS platforms, offering …

- [Transaction Authorization Cheat Sheet](Transaction_Authorization_Cheat_Sheet.md)
  - `ASVS V6.5 V8.3 V15.4: · PC C7 · Top10 A01 · MASVS MASVS-AUTH`
  - This cheat sheet discusses how developers can secure transaction authorizations and prevent them from being bypassed. These guidelines are for:

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
