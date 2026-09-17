# 02_输入验证、注入与文件处理

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：所有「不可信输入 → 危险汇聚点」类缺陷的防御：输入校验，SQL／命令／LDAP／NoSQL／XML 注入，XSS 输出编码，反序列化，文件上传，批量赋值，原型污染，SSRF。

**文档数**：18

- [Bean Validation Cheat Sheet](Bean_Validation_Cheat_Sheet.md)
  - `ASVS V1.2 · PC C5`
  - This article is focused on providing clear, simple, actionable guidance for providing Java Bean Validation security functionality in your applications. Bean validation (aka Jakarta Validation) is one …

- [Cross Site Scripting Prevention Cheat Sheet](Cross_Site_Scripting_Prevention_Cheat_Sheet.md)
  - `ASVS V1.1 V1.2 V1.3 · PC C4 · Top10 A03`
  - This cheat sheet helps developers prevent XSS vulnerabilities. Cross-Site Scripting (XSS) is a misnomer. Originally this term was derived from early versions of the attack that were primarily focused …

- [DOM based XSS Prevention Cheat Sheet](DOM_based_XSS_Prevention_Cheat_Sheet.md)
  - `ASVS V1.2 V1.3 · PC C4 · Top10 A03`
  - When looking at XSS (Cross-Site Scripting), there are three generally recognized forms of XSS:

- [Deserialization Cheat Sheet](Deserialization_Cheat_Sheet.md)
  - `ASVS V1.5 · PC C5 · Top10 A08 · MASVS MASVS-CODE`
  - This article is focused on providing clear, actionable guidance for safely deserializing untrusted data in your applications. However, many programming languages have native ways to serialize objects.…

- [File Upload Cheat Sheet](File_Upload_Cheat_Sheet.md)
  - `ASVS V1.2 V5.1 V5.2 V5.4 · PC C5`
  - File upload is becoming a more and more essential part of any application, where the user is able to upload their photo, their CV, or a video showcasing a project they are working on. The application …

- [Injection Prevention Cheat Sheet](Injection_Prevention_Cheat_Sheet.md)
  - `ASVS V1.2 V1.3 · PC C4 C5 · Top10 A03 · MASVS MASVS-CODE`
  - This article is focused on providing clear, simple, actionable guidance for preventing the entire category of Injection flaws in your applications. Injection attacks, especially SQL Injection, are unf…

- [Input Validation Cheat Sheet](Input_Validation_Cheat_Sheet.md)
  - `ASVS V1.2 V1.3 V2.2 V5.1 V5.2 V5.3 · PC C5 · MASVS MASVS-CODE`
  - This article is focused on providing clear, simple, actionable guidance for providing Input Validation security functionality in your applications. Input validation is performed to ensure only properl…

- [LDAP Injection Prevention Cheat Sheet](LDAP_Injection_Prevention_Cheat_Sheet.md)
  - `ASVS V1.2 V1.3 · PC C4 · Top10 A03`
  - The Lightweight Directory Access Protocol (LDAP) allows an application to remotely perform operations such as searching and modifying records in directories. LDAP injection results from inadequate inp…

- [Mass Assignment Cheat Sheet](Mass_Assignment_Cheat_Sheet.md)
  - `ASVS V15.3: · PC C5`
  - Software frameworks sometimes allow developers to automatically bind HTTP request parameters into program code variables or objects to make using that framework easier on developers. This can sometime…

- [NoSQL Security Cheat Sheet](NoSQL_Security_Cheat_Sheet.md)
  - `—`
  - NoSQL databases (MongoDB, CouchDB, Cassandra etc.) power many modern applications with flexible schemas and horizontal scale. But their different query models and deployment patterns create more secur…

- [OS Command Injection Defense Cheat Sheet](OS_Command_Injection_Defense_Cheat_Sheet.md)
  - `ASVS V1.2 · PC C5 · Top10 A03 · MASVS MASVS-CODE`
  - Command injection (or OS Command Injection) is a type of injection where software that constructs a system command using externally influenced input does not correctly neutralize the input from specia…

- [Prototype Pollution Prevention Cheat Sheet](Prototype_Pollution_Prevention_Cheat_Sheet.md)
  - `ASVS V15.3:`
  - Prototype Pollution is a critical vulnerability that can allow attackers to manipulate an application's JavaScript objects and properties, leading to serious security issues such as unauthorized acces…

- [Query Parameterization Cheat Sheet](Query_Parameterization_Cheat_Sheet.md)
  - `ASVS V1.2 · PC C3 · Top10 A03 · MASVS MASVS-CODE`
  - SQL Injection is one of the most dangerous web vulnerabilities. As of the OWASP Top 10:2025, it is categorized under A05:2025-Injection. It represents a serious threat because SQL Injection allows evi…

- [SQL Injection Prevention Cheat Sheet](SQL_Injection_Prevention_Cheat_Sheet.md)
  - `ASVS V1.2 · PC C3 · Top10 A03 · MASVS MASVS-CODE`
  - This cheat sheet will help you prevent SQL injection flaws in your applications. It will define what SQL injection is, explain where those flaws occur, and provide four options for defending against S…

- [Server-Side Request Forgery Prevention Cheat Sheet](Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
  - `ASVS V1.3 V1.5 V5.3 V13.1 V13.2 · PC C5 · Top10 A10`
  - The objective of the cheat sheet is to provide advice regarding the protection against Server Side Request Forgery (SSRF) attack. This cheat sheet will focus on the defensive point of view and will no…

- [XML External Entity Prevention Cheat Sheet](XML_External_Entity_Prevention_Cheat_Sheet.md)
  - `ASVS V1.2 V1.3 V1.5 · PC C5 · Top10 A05 · MASVS MASVS-CODE`
  - An _XML eXternal Entity injection_ (XXE), which is now part of the OWASP Top 10 via the point A4 , is attack against applications that parse XML input. This issue is referenced in the ID 611 in the Co…

- [XML Security Cheat Sheet](XML_Security_Cheat_Sheet.md)
  - `ASVS V1.2 V1.5 · MASVS MASVS-CODE`
  - While the specifications for XML and XML schemas provide you with the tools needed to protect XML applications, they also include multiple security flaws. They can be exploited to perform multiple typ…

- [XSS Filter Evasion Cheat Sheet](XSS_Filter_Evasion_Cheat_Sheet.md)
  - `ASVS V1.2 · Top10 A03`
  - This article is a guide to Cross Site Scripting (XSS) testing for application security professionals. This cheat sheet was originally based on RSnake's seminal XSS Cheat Sheet previously at: http://ha…

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
