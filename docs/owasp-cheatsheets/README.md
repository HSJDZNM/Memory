# OWASP 代码安全指南文档库（本地层级化存档）

从 OWASP Cheat Sheet Series 的 **Secure Code Review Cheat Sheet** 出发，沿页面内的超链接爬取，并逐篇阅读正文后判定取舍，最终保留的「代码安全指南」文档，按安全领域做了层级化归档。

| 项目 | 内容 |
| --- | --- |
| 种子页 | <https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html> |
| 站点 | OWASP Cheat Sheet Series（<https://cheatsheetseries.owasp.org/>） |
| 抓取工具 | Crawl4AI 0.9.3，`AsyncHTTPCrawlerStrategy` 纯 HTTP 策略（站点为静态 MkDocs，无需浏览器） |
| 抓取时间 | 2026-09-16 |
| 候选文档 | 122 篇（种子页导航与正文中出现的全部 cheatsheet 链接） |
| 保留 | **118 篇** |
| 排除 | 4 篇（已废弃的跳转占位页，内容已迁移） |
| 另附 | `00_索引与标准/` 下 6 个站点索引页，用于导航与交叉引用 |

---

## 一、层级总览

```text
owasp-cheatsheets/
├── README.md            ← 本文件（库总览与逐篇索引）
├── STRUCTURE.md         ← 层级依据、完整对照表、引用关系
├── manifest.json        ← 机器可读清单（含 sha256）
├── 00_索引与标准/                  ← 站点自带的 6 个索引页（非指南正文）
├── 01_安全需求、架构与治理/
├── 02_输入验证、注入与文件处理/
├── 03_Web前端与浏览器安全/
├── 04_API、微服务与Web服务安全/
├── 05_身份认证与会话管理/
├── 06_授权与访问控制/
├── 07_令牌、联合身份与密码学/
├── 08_传输层、网络与数据保护/
├── 09_供应链与依赖安全/
├── 10_日志、监控与错误处理/
├── 11_业务逻辑与反自动化/
├── 12_编程语言与框架专项/
│   ├── .NET/
│   ├── JavaScript与TypeScript/
│   ├── Java与C系/
│   ├── PHP与Ruby/
│   ├── Python/
├── 13_云原生、容器与基础设施/
│   ├── CI-CD与IaC/
│   ├── 云架构与零信任/
│   ├── 容器与编排/
├── 14_AI与LLM应用安全/
├── 15_移动与嵌入式安全/
└── LICENSE.txt          ← CC BY-SA 4.0
```

---

## 二、文档索引（按层级）

### 01_安全需求、架构与治理（11 篇）

> 开发早期的安全需求、威胁建模、攻击面分析、安全设计、安全术语，以及遗留系统、漏洞披露、虚拟补丁、第三方支付集成等治理类指南。

- **[Abuse Case Cheat Sheet (Historical)](01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md)**
  - 交叉引用：ASVS V2.1 V2.3 V14.1 V15.1: · PC C1 · Top10 A04 · MASVS MASVS-RESILIENCE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html>
- **[Attack Surface Analysis Cheat Sheet](01_安全需求、架构与治理/Attack_Surface_Analysis_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.1: · PC C1 · Top10 A04 · MASVS MASVS-PLATFORM MASVS-RESILIENCE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html>
- **[Legacy Application Management Cheat Sheet](01_安全需求、架构与治理/Legacy_Application_Management_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Legacy_Application_Management_Cheat_Sheet.html>
- **[Microservices based Security Arch Doc Cheat Sheet](01_安全需求、架构与治理/Microservices_based_Security_Arch_Doc_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Microservices_based_Security_Arch_Doc_Cheat_Sheet.html>
- **[Secure Code Review Cheat Sheet](01_安全需求、架构与治理/Secure_Code_Review_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.4:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html>
- **[Secure Product Design Cheat Sheet](01_安全需求、架构与治理/Secure_Product_Design_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secure_Product_Design_Cheat_Sheet.html>
- **[Security Terminology Cheat Sheet](01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.1 V6.1 V8.1 V11.1 V15.1:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Security_Terminology_Cheat_Sheet.html>
- **[Secure Integration of Third-Party Payment Gateways Cheat Sheet](01_安全需求、架构与治理/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.html>
- **[Threat Modeling Cheat Sheet](01_安全需求、架构与治理/Threat_Modeling_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.1: · PC C1 · Top10 A04 · MASVS MASVS-RESILIENCE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html>
- **[Virtual Patching Cheat Sheet](01_安全需求、架构与治理/Virtual_Patching_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.2:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Virtual_Patching_Cheat_Sheet.html>
- **[Vulnerability Disclosure Cheat Sheet](01_安全需求、架构与治理/Vulnerability_Disclosure_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html>

### 02_输入验证、注入与文件处理（18 篇）

> 所有「不可信输入 → 危险汇聚点」类缺陷的防御：输入校验，SQL／命令／LDAP／NoSQL／XML 注入，XSS 输出编码，反序列化，文件上传，批量赋值，原型污染，SSRF。

- **[Bean Validation Cheat Sheet](02_输入验证、注入与文件处理/Bean_Validation_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 · PC C5
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Bean_Validation_Cheat_Sheet.html>
- **[Cross Site Scripting Prevention Cheat Sheet](02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.1 V1.2 V1.3 · PC C4 · Top10 A03
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html>
- **[DOM based XSS Prevention Cheat Sheet](02_输入验证、注入与文件处理/DOM_based_XSS_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.3 · PC C4 · Top10 A03
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html>
- **[Deserialization Cheat Sheet](02_输入验证、注入与文件处理/Deserialization_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.5 · PC C5 · Top10 A08 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html>
- **[File Upload Cheat Sheet](02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V5.1 V5.2 V5.4 · PC C5
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html>
- **[Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/Injection_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.3 · PC C4 C5 · Top10 A03 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html>
- **[Input Validation Cheat Sheet](02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.3 V2.2 V5.1 V5.2 V5.3 · PC C5 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html>
- **[LDAP Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/LDAP_Injection_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.3 · PC C4 · Top10 A03
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html>
- **[Mass Assignment Cheat Sheet](02_输入验证、注入与文件处理/Mass_Assignment_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.3: · PC C5
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html>
- **[NoSQL Security Cheat Sheet](02_输入验证、注入与文件处理/NoSQL_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Security_Cheat_Sheet.html>
- **[OS Command Injection Defense Cheat Sheet](02_输入验证、注入与文件处理/OS_Command_Injection_Defense_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 · PC C5 · Top10 A03 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html>
- **[Prototype Pollution Prevention Cheat Sheet](02_输入验证、注入与文件处理/Prototype_Pollution_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.3:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.html>
- **[Query Parameterization Cheat Sheet](02_输入验证、注入与文件处理/Query_Parameterization_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 · PC C3 · Top10 A03 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html>
- **[SQL Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/SQL_Injection_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 · PC C3 · Top10 A03 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html>
- **[Server-Side Request Forgery Prevention Cheat Sheet](02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.3 V1.5 V5.3 V13.1 V13.2 · PC C5 · Top10 A10
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html>
- **[XML External Entity Prevention Cheat Sheet](02_输入验证、注入与文件处理/XML_External_Entity_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.3 V1.5 · PC C5 · Top10 A05 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html>
- **[XML Security Cheat Sheet](02_输入验证、注入与文件处理/XML_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 V1.5 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html>
- **[XSS Filter Evasion Cheat Sheet](02_输入验证、注入与文件处理/XSS_Filter_Evasion_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2 · Top10 A03
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/XSS_Filter_Evasion_Cheat_Sheet.html>

### 03_Web前端与浏览器安全（13 篇）

> 浏览器侧安全控制：CSP、安全响应头、点击劫持、HTML5、DOM 冲突、CSRF、XS-Leaks、CSS 安全、AJAX、第三方 JS 管理、HSTS、开放重定向、浏览器扩展。

- **[AJAX Security Cheat Sheet](03_Web前端与浏览器安全/AJAX_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/AJAX_Security_Cheat_Sheet.html>
- **[Browser Extension Security Vulnerabilities Cheat Sheet](03_Web前端与浏览器安全/Browser_Extension_Vulnerabilities_Cheat_Sheet.md)**
  - 交叉引用：ASVS V10.7
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Browser_Extension_Vulnerabilities_Cheat_Sheet.html>
- **[Clickjacking Defense Cheat Sheet](03_Web前端与浏览器安全/Clickjacking_Defense_Cheat_Sheet.md)**
  - 交叉引用：PC C2
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html>
- **[Content Security Policy Cheat Sheet](03_Web前端与浏览器安全/Content_Security_Policy_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.1 · Top10 A03
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html>
- **[Cross-Site Request Forgery Prevention Cheat Sheet](03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.3 V3.1 V3.2 V3.3 V3.4 V3.5 V3.7 V4.1 · PC C7 · Top10 A01
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html>
- **[DOM Clobbering Prevention Cheat Sheet](03_Web前端与浏览器安全/DOM_Clobbering_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.2
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/DOM_Clobbering_Prevention_Cheat_Sheet.html>
- **[HTML5 Security Cheat Sheet](03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.2 V3.4 V3.5 V14.2 V14.3
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html>
- **[HTTP Security Response Headers Cheat Sheet](03_Web前端与浏览器安全/HTTP_Headers_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html>
- **[HTTP Strict Transport Security Cheat Sheet](03_Web前端与浏览器安全/HTTP_Strict_Transport_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.1 V3.4 V3.7 · PC C8 · Top10 A02 · MASVS MASVS-NETWORK
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html>
- **[Securing Cascading Style Sheets Cheat Sheet](03_Web前端与浏览器安全/Securing_Cascading_Style_Sheets_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Securing_Cascading_Style_Sheets_Cheat_Sheet.html>
- **[Third Party JavaScript Management Cheat Sheet](03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.2 V3.6 V3.7 V15.1: V15.2: · Top10 A06
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html>
- **[Unvalidated Redirects and Forwards Cheat Sheet](03_Web前端与浏览器安全/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.7 V10.4 V15.3: · PC C5
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html>
- **[Cross-site leaks Cheat Sheet](03_Web前端与浏览器安全/XS_Leaks_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/XS_Leaks_Cheat_Sheet.html>

### 04_API、微服务与Web服务安全（7 篇）

> 服务间与对外接口的安全：REST、GraphQL、gRPC、WebSocket、Web Service（SOAP）、微服务架构安全。

- **[GraphQL Cheat Sheet](04_API、微服务与Web服务安全/GraphQL_Cheat_Sheet.md)**
  - 交叉引用：ASVS V4.3
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html>
- **[Microservices Security Cheat Sheet](04_API、微服务与Web服务安全/Microservices_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V2.2 V11.7
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html>
- **[REST Assessment Cheat Sheet](04_API、微服务与Web服务安全/REST_Assessment_Cheat_Sheet.md)**
  - 交叉引用：ASVS V4.1
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html>
- **[REST Security Cheat Sheet](04_API、微服务与Web服务安全/REST_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V4.1 V4.2 V9.2 · MASVS MASVS-NETWORK
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html>
- **[WebSocket Security Cheat Sheet](04_API、微服务与Web服务安全/WebSocket_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V4.4
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>
- **[Web Service Security Cheat Sheet](04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V2.2 V4.1 V4.2 · MASVS MASVS-NETWORK
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Web_Service_Security_Cheat_Sheet.html>
- **[gRPC Security Cheat Sheet](04_API、微服务与Web服务安全/gRPC_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/gRPC_Security_Cheat_Sheet.html>

### 05_身份认证与会话管理（10 篇）

> 身份认证与会话全生命周期：认证、口令存储、多因素认证、忘记密码、安全问题、撞库防护、邮箱验证、JAAS、会话管理、Cookie 窃取缓解。

- **[Authentication Cheat Sheet](05_身份认证与会话管理/Authentication_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.2 V6.3 V6.5 V6.7 V6.8 · PC C6 · Top10 A07 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html>
- **[Choosing and Using Security Questions Cheat Sheet](05_身份认证与会话管理/Choosing_and_Using_Security_Questions_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.4 · PC C6 · Top10 A07
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html>
- **[Cookie Theft Mitigation Cheat Sheet](05_身份认证与会话管理/Cookie_Theft_Mitigation_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Cookie_Theft_Mitigation_Cheat_Sheet.html>
- **[Credential Stuffing Prevention Cheat Sheet](05_身份认证与会话管理/Credential_Stuffing_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.1 V6.3 · PC C7 · Top10 A07 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html>
- **[Email Validation and Verification in Identity Systems Cheat Sheet](05_身份认证与会话管理/Email_Validation_and_Verification_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html>
- **[Forgot Password Cheat Sheet](05_身份认证与会话管理/Forgot_Password_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.3 V6.4 V6.6 · PC C6 · Top10 A07
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html>
- **[JAAS Cheat Sheet](05_身份认证与会话管理/JAAS_Cheat_Sheet.md)**
  - 交叉引用：PC C6
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/JAAS_Cheat_Sheet.html>
- **[Multifactor Authentication Cheat Sheet](05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.4 V6.5 V6.6 V6.7 · PC C6 C7 · Top10 A07
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html>
- **[Password Storage Cheat Sheet](05_身份认证与会话管理/Password_Storage_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.5 V11.4 · PC C6 · Top10 A07 · MASVS MASVS-STORAGE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>
- **[Session Management Cheat Sheet](05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.3 V7: V7.1 V7.2 V7.3 V7.4 V7.5 V7.6 V8.2 V16.2: · PC C6 · Top10 A07 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>

### 06_授权与访问控制（6 篇）

> 授权模型与访问控制实现：通用授权、IDOR、事务授权、多租户隔离，以及授权的自动化测试与回归测试。

- **[Authorization Cheat Sheet](06_授权与访问控制/Authorization_Cheat_Sheet.md)**
  - 交叉引用：ASVS V8.1 V8.2 V8.4 V16.3: · Top10 A01 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>
- **[Authorization Regression Testing Cheat Sheet](06_授权与访问控制/Authorization_Regression_Testing_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Regression_Testing_Cheat_Sheet.html>
- **[Authorization Testing Automation Cheat Sheet](06_授权与访问控制/Authorization_Testing_Automation_Cheat_Sheet.md)**
  - 交叉引用：ASVS V8.1 · PC C7
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation_Cheat_Sheet.html>
- **[Insecure Direct Object Reference Prevention Cheat Sheet](06_授权与访问控制/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.md)**
  - 交叉引用：ASVS V8.2 · PC C7 · Top10 A01 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html>
- **[Multi-Tenant Application Security Cheat Sheet](06_授权与访问控制/Multi_Tenant_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V8.4
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html>
- **[Transaction Authorization Cheat Sheet](06_授权与访问控制/Transaction_Authorization_Cheat_Sheet.md)**
  - 交叉引用：ASVS V6.5 V8.3 V15.4: · PC C7 · Top10 A01 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html>

### 07_令牌、联合身份与密码学（6 篇）

> 自包含令牌与联邦身份（JWT、SAML、OAuth 2.0／OIDC），以及加密存储、密钥管理、机密信息管理。

- **[Cryptographic Storage Cheat Sheet](07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)**
  - 交叉引用：ASVS V11.1 V11.2 V11.3 V11.5 V13.3 V14.1 · PC C8 · Top10 A02 · MASVS MASVS-CRYPTO MASVS-STORAGE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html>
- **[JSON Web Token Cheat Sheet](07_令牌、联合身份与密码学/JSON_Web_Token_Cheat_Sheet.md)**
  - 交叉引用：ASVS V9.1 · PC C6 · Top10 A07 · MASVS MASVS-AUTH
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html>
- **[Key Management Cheat Sheet](07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md)**
  - 交叉引用：ASVS V11.1 V11.3 V11.7 V13.3 · PC C8 · Top10 A02 · MASVS MASVS-CRYPTO
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html>
- **[OAuth 2.0 Protocol Cheatsheet](07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)**
  - 交叉引用：ASVS V10.1 V10.2 V10.3 V10.4 V10.5 V10.6
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html>
- **[SAML Security Cheat Sheet](07_令牌、联合身份与密码学/SAML_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V9.1 · PC C6 · Top10 A07
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html>
- **[Secrets Management Cheat Sheet](07_令牌、联合身份与密码学/Secrets_Management_Cheat_Sheet.md)**
  - 交叉引用：ASVS V11.7 · Top10 A02 · MASVS MASVS-STORAGE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html>

### 08_传输层、网络与数据保护（5 篇）

> 传输层与网络层防护（TLS、证书／公钥固定、网络分段），以及数据库安全配置与用户隐私保护。

- **[Database Security Cheat Sheet](08_传输层、网络与数据保护/Database_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html>
- **[Network segmentation Cheat Sheet](08_传输层、网络与数据保护/Network_Segmentation_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Network_Segmentation_Cheat_Sheet.html>
- **[Pinning Cheat Sheet](08_传输层、网络与数据保护/Pinning_Cheat_Sheet.md)**
  - 交叉引用：PC C8 · Top10 A02 · MASVS MASVS-NETWORK
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Pinning_Cheat_Sheet.html>
- **[Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V3.3 V4.1 V4.4 V10.3 V10.4 V11.6 V12.1 V12.2 V12.3 V17.2 · PC C8 · Top10 A02 · MASVS MASVS-NETWORK
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html>
- **[User Privacy Protection Cheat Sheet](08_传输层、网络与数据保护/User_Privacy_Protection_Cheat_Sheet.md)**
  - 交叉引用：ASVS V14.1 V14.2 · PC C8 · MASVS MASVS-PRIVACY
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html>

### 09_供应链与依赖安全（4 篇）

> 软件供应链、SBOM、易受攻击依赖管理，以及 NPM 包管理安全最佳实践。

- **[Dependency Graph & SBOM Best Practices Cheat Sheet](09_供应链与依赖安全/Dependency_Graph_SBOM_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.1:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Dependency_Graph_SBOM_Cheat_Sheet.html>
- **[NPM Security best practices](09_供应链与依赖安全/NPM_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V13.4 · Top10 A06
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html>
- **[Software Supply Chain Security](09_供应链与依赖安全/Software_Supply_Chain_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.1: V15.2:
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html>
- **[Vulnerable Dependency Management Cheat Sheet](09_供应链与依赖安全/Vulnerable_Dependency_Management_Cheat_Sheet.md)**
  - 交叉引用：ASVS V15.2: · PC C2 · Top10 A06 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html>

### 10_日志、监控与错误处理（3 篇）

> 安全日志记录、日志词汇规范、日志保护与错误处理。

- **[Error Handling Cheat Sheet](10_日志、监控与错误处理/Error_Handling_Cheat_Sheet.md)**
  - 交叉引用：ASVS V16.5: · PC C10 · MASVS MASVS-CODE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html>
- **[Logging Cheat Sheet](10_日志、监控与错误处理/Logging_Cheat_Sheet.md)**
  - 交叉引用：ASVS V10.7 V16.1: V16.2: V16.3: V16.4: · PC C9 · Top10 A09 · MASVS MASVS-CODE MASVS-STORAGE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html>
- **[Application Logging Vocabulary Cheat Sheet](10_日志、监控与错误处理/Logging_Vocabulary_Cheat_Sheet.md)**
  - 交叉引用：ASVS V16.1: V16.3: · Top10 A09
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html>

### 11_业务逻辑与反自动化（3 篇）

> 业务逻辑缺陷、拒绝服务，以及机器人流量与自动化滥用治理。

- **[Bot Management and Anti-Automation Cheat Sheet](11_业务逻辑与反自动化/Bot_Management_and_Anti-Automation_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html>
- **[Business Logic Security Cheat Sheet](11_业务逻辑与反自动化/Business_Logic_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html>
- **[Denial of Service Cheat Sheet](11_业务逻辑与反自动化/Denial_of_Service_Cheat_Sheet.md)**
  - 交叉引用：ASVS V2.4 · Top10 A07 A11
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html>

### 12_编程语言与框架专项（11 篇）

> 面向具体语言／框架的落地清单；二级目录按技术栈划分。

#### .NET

- **[DotNet Security Cheat Sheet](12_编程语言与框架专项/.NET/DotNet_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/DotNet_Security_Cheat_Sheet.html>

#### JavaScript与TypeScript

- **[Next.js Security Cheat Sheet](12_编程语言与框架专项/JavaScript与TypeScript/Nextjs_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Nextjs_Security_Cheat_Sheet.html>
- **[NodeJS Security Cheat Sheet](12_编程语言与框架专项/JavaScript与TypeScript/Nodejs_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html>

#### Java与C系

- **[C-Based Toolchain Hardening Cheat Sheet](12_编程语言与框架专项/Java与C系/C-Based_Toolchain_Hardening_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/C-Based_Toolchain_Hardening_Cheat_Sheet.html>
- **[Java Security Cheat Sheet](12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V1.2
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Java_Security_Cheat_Sheet.html>

#### PHP与Ruby

- **[Laravel Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md)**
  - 交叉引用：ASVS V13.4
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html>
- **[PHP Configuration Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/PHP_Configuration_Cheat_Sheet.md)**
  - 交叉引用：PC C2 · Top10 A05
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/PHP_Configuration_Cheat_Sheet.html>
- **[Ruby on Rails Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Ruby_on_Rails_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Ruby_on_Rails_Cheat_Sheet.html>
- **[Symfony Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Symfony_Cheat_Sheet.md)**
  - 交叉引用：ASVS V13.4
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Symfony_Cheat_Sheet.html>

#### Python

- **[Django REST Framework (DRF) Cheat Sheet](12_编程语言与框架专项/Python/Django_REST_Framework_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Django_REST_Framework_Cheat_Sheet.html>
- **[Django Security Cheat Sheet](12_编程语言与框架专项/Python/Django_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Django_Security_Cheat_Sheet.html>

### 13_云原生、容器与基础设施（10 篇）

> 容器与编排、CI/CD 与基础设施即代码、云架构与零信任；二级目录按平台划分。

#### CI-CD与IaC

- **[CI/CD Security Cheat Sheet](13_云原生、容器与基础设施/CI-CD与IaC/CI_CD_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html>
- **[GitHub Actions Security Cheat Sheet](13_云原生、容器与基础设施/CI-CD与IaC/GitHub_Actions_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/GitHub_Actions_Security_Cheat_Sheet.html>
- **[Infrastructure as Code Security Cheatsheet](13_云原生、容器与基础设施/CI-CD与IaC/Infrastructure_as_Code_Security_Cheat_Sheet.md)**
  - 交叉引用：Top10 A05
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Infrastructure_as_Code_Security_Cheat_Sheet.html>

#### 云架构与零信任

- **[Cloud Architecture Security Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Secure_Cloud_Architecture_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secure_Cloud_Architecture_Cheat_Sheet.html>
- **[Serverless / FaaS Security Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Serverless_FaaS_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Serverless_FaaS_Security_Cheat_Sheet.html>
- **[Subdomain Takeover Prevention Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Subdomain_Takeover_Prevention_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Subdomain_Takeover_Prevention_Cheat_Sheet.html>
- **[Zero Trust Architecture Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Zero_Trust_Architecture_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Zero_Trust_Architecture_Cheat_Sheet.html>

#### 容器与编排

- **[Docker Security Cheat Sheet](13_云原生、容器与基础设施/容器与编排/Docker_Security_Cheat_Sheet.md)**
  - 交叉引用：ASVS V13.2 · Top10 A05
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html>
- **[Kubernetes Security Cheat Sheet](13_云原生、容器与基础设施/容器与编排/Kubernetes_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html>
- **[Node.js Docker Cheat Sheet](13_云原生、容器与基础设施/容器与编排/NodeJS_Docker_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/NodeJS_Docker_Cheat_Sheet.html>

### 14_AI与LLM应用安全（8 篇）

> LLM 提示注入、RAG、MCP、AI Agent、AI 模型运维，以及「用 AI 写代码」的安全指南。

- **[AI-Powered Advertising Systems Security Cheat Sheet](14_AI与LLM应用安全/AI-Powered_Advertising_Systems_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/AI-Powered_Advertising_Systems_Security_Cheat_Sheet.html>
- **[AI Agent Security Cheat Sheet](14_AI与LLM应用安全/AI_Agent_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html>
- **[AML and Sanctions Compliance for AI Agent Payments Cheat Sheet](14_AI与LLM应用安全/AML_Sanctions_AI_Agent_Payments_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/AML_Sanctions_AI_Agent_Payments_Cheat_Sheet.html>
- **[LLM Prompt Injection Prevention Cheat Sheet](14_AI与LLM应用安全/LLM_Prompt_Injection_Prevention_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html>
- **[MCP (Model Context Protocol) Security Cheat Sheet](14_AI与LLM应用安全/MCP_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html>
- **[Retrieval-Augmented Generation (RAG) Security Cheat Sheet](14_AI与LLM应用安全/RAG_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html>
- **[Secure AI/ML Model Ops Cheat Sheet](14_AI与LLM应用安全/Secure_AI_Model_Ops_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secure_AI_Model_Ops_Cheat_Sheet.html>
- **[Secure Coding with AI Cheat Sheet](14_AI与LLM应用安全/Secure_Coding_with_AI_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html>

### 15_移动与嵌入式安全（3 篇）

> 移动应用、汽车、无人机等终端与嵌入式场景的安全指南。

- **[Top 10 Automotive Security Vulnerabilities](15_移动与嵌入式安全/Automotive_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Automotive_Security_Cheat_Sheet.html>
- **[Drone Security Cheat Sheet](15_移动与嵌入式安全/Drone_Security_Cheat_Sheet.md)**
  - 交叉引用：—
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Drone_Security_Cheat_Sheet.html>
- **[Mobile Application Security Cheat Sheet](15_移动与嵌入式安全/Mobile_Application_Security_Cheat_Sheet.md)**
  - 交叉引用：MASVS MASVS-RESILIENCE
  - 来源：<https://cheatsheetseries.owasp.org/cheatsheets/Mobile_Application_Security_Cheat_Sheet.html>

---

## 三、层级划分依据

划分以 **OWASP ASVS 5.0 的验证章节（V1–V17）** 为主干——安全代码评审本身就是按 ASVS 逐条核对代码的过程——并针对 ASVS 未覆盖的技术栈、平台与新兴领域增设专项分支：

- **01–11 类**：对应 ASVS 的通用安全控制维度（需求与设计 V15.1；输入与注入 V1–V2；前端 V3；API V4；文件 V5；认证 V6；会话 V7；授权 V8；令牌 V9–V10；密码学 V11；传输 V12；数据保护 V14；供应链 V15.2；日志 V16）。
- **12–15 类**：ASVS 未覆盖的领域——编程语言与框架、云原生与基础设施、AI/LLM、移动与嵌入式。
- 每篇文档**只归档一次**（主分类）；它在 ASVS／Top 10／Proactive Controls／MASVS 中的**全部归属**记录在文首元数据与各目录 README 中，完整对照表见 `STRUCTURE.md`，机器可读版本见 `manifest.json`。

> 说明：OWASP 的 ASVS 索引会把同一篇 cheat sheet 映射到多个子章节（例如 Session Management 同时属于 V3、V7、V8、V16）。本库取「最能代表该文档主题」的单一主分类，而非机械取最小章节号，以避免 Logging 被归入 V10（OAuth）、Transport Layer Security 被归入 V3（Web 前端）这类明显失真的归档。

---

## 四、判定与排除记录

爬取全部 122 个候选链接后逐篇阅读正文，**排除 4 篇**：它们不是安全指南正文，而是指向新位置的废弃占位页。

| 已废弃文档 | 抓取到的内容 | 迁移去向 | 处理 |
| --- | --- | --- | --- |
| Access Control Cheat Sheet | 「DEPRECATED: The Access Control cheatsheet has been deprecated.」（约 220 字符） | [Authorization Cheat Sheet](06_授权与访问控制/Authorization_Cheat_Sheet.md) | 不保存 |
| TLS Cipher String Cheat Sheet | 「DEPRECATED: ... Please visit the Transport Layer Security Cheat Sheet instead.」（约 250 字符） | [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) | 不保存 |
| Transport Layer Protection Cheat Sheet | 同上（约 270 字符） | [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) | 不保存 |
| Injection Prevention in Java Cheat Sheet | 「This information has been moved to the dedicated Java Security CheatSheet」（约 230 字符） | [Java Security Cheat Sheet](12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md) | 不保存 |

保留的 118 篇均具备完整正文。文档正文中指向上述废弃页的链接保留为 OWASP 线上地址，便于溯源。

---

## 五、未纳入范围的外部链接

种子页还指向以下**站外**资源；它们不属于 OWASP Cheat Sheet Series 的 cheat sheet，故未抓取，仅登记备查：

- <https://csrc.nist.gov/Projects/ssdf>
- <https://cwe.mitre.org/top25/>
- <https://owasp.org/www-project-application-security-verification-standard/>
- <https://owasp.org/www-project-code-review-guide/>
- <https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/>
- <https://owasp.org/www-project-top-ten/>
- <https://owasp.org/www-project-web-security-testing-guide/>
- <https://wiki.sei.cmu.edu/confluence/display/seccode>
- <https://www.iso.org/standard/44378.html>
- <https://www.microsoft.com/en-us/securityengineering/sdl/>

---

## 六、使用与复核

- 每篇文档文首带有 HTML 注释形式的元数据（source／fetched／category／crosswalk），在渲染视图中不可见，但可被 grep 检索。
- 文档之间的 OWASP 站内链接已重写为**相对路径**，离线状态下可直接互跳；站外链接保持原样。
- 复现方式见下文「七、复现」，或直接运行 `python tools/owasp_cheatsheets/pipeline.py all`。

---

## 七、复现

本库由仓库内的 `tools/owasp_cheatsheets/` 流水线生成，全部脚本使用 crawl4ai 的纯 HTTP 策略（不启动浏览器）：

```text
python tools/owasp_cheatsheets/pipeline.py all

  01_analyze.py   解析站点四个索引页 -> _work/owasp-cheatsheets/taxonomy.json
  02_fetch.py     抓取 122 篇文档 + 6 个索引页 -> _work/owasp-cheatsheets/{content/,meta.json}
  03_build.py     按层级写入 -> docs/owasp-cheatsheets/（并改写站内链接为相对路径）
  04_index.py     生成 README/STRUCTURE/manifest/LICENSE，并统一换行与编码
  05_verify.py    校验链接完整性、编码、换行与 manifest 校验和
```

中间产物位于 `_work/owasp-cheatsheets/`，可随时删除后重跑。

---

抓取时间：2026-09-16 · 内容版权归 OWASP Foundation 所有（CC BY-SA 4.0）。
