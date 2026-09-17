# 文档关系与层级

本目录收录 OWASP Cheat Sheet Series 中与安全代码评审相关的 **118 篇指南**，外加站点自带的 6 个索引页。层级划分的结论来自 OWASP 站点自身公布的四个索引页，不含人工臆测：

- IndexASVS -> OWASP ASVS 5.0 章节（V1–V17）
- IndexProactiveControls -> OWASP Top 10 Proactive Controls 2018（C1–C10）
- IndexTopTen -> OWASP Top 10 2021（A01–A11）
- IndexMASVS -> MASVS（STORAGE／CRYPTO／AUTH／NETWORK／PLATFORM／CODE／RESILIENCE／PRIVACY）

## 1. 层级结构

```text
owasp-cheatsheets/
├── README.md            # 库总览与逐篇索引
├── STRUCTURE.md         # 本文件：层级依据、完整对照表、引用关系
├── manifest.json        # 机器可读清单（local_path / source_url / crosswalk / sha256）
├── LICENSE.txt          # CC BY-SA 4.0
├── 00_索引与标准/
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
```

## 2. 与上游 URL 路径的关系

仓库内既有的两份镜像（`docs/google-eng-practices`、`docs/gitlab-code-review`）遵循「本地目录与 URL 路径严格一一对应」。**本库是有意的例外**：本任务要求按安全领域做层级划分，因此物理目录按主题重排，不再等于上游 URL 路径。

代价与补偿：

- URL 与本地路径的对应关系不再能从路径直接读出，改由 `manifest.json` 的 `source_url` / `local_path` 逐页维护。
- 文档之间的站内链接已在正文中改写为相对路径，重排不影响离线浏览；`05_verify.py` 会逐条校验。
- 站点自身的 6 个索引页保留在 `00_索引与标准/`，用于回溯上游分类。
- 上游 Markdown 源文件路径记录在 `source_repo_path`（已抽查验证：`cheatsheets/<Name>_Cheat_Sheet.md` 与四个 Index 页返回 200；`Glossary` 由站点生成，无对应源文件，记为 null）。

## 3. 分类范围与文档数

| 分类 | 文档数 | 收录范围 |
| --- | --- | --- |
| 01_安全需求、架构与治理 | 11 | 开发早期的安全需求、威胁建模、攻击面分析、安全设计、安全术语，以及遗留系统、漏洞披露、虚拟补丁、第三方支付集成等治理类指南。 |
| 02_输入验证、注入与文件处理 | 18 | 所有「不可信输入 → 危险汇聚点」类缺陷的防御：输入校验，SQL／命令／LDAP／NoSQL／XML 注入，XSS 输出编码，反序列化，文件上传，批量赋值，原型污染，SSRF。 |
| 03_Web前端与浏览器安全 | 13 | 浏览器侧安全控制：CSP、安全响应头、点击劫持、HTML5、DOM 冲突、CSRF、XS-Leaks、CSS 安全、AJAX、第三方 JS 管理、HSTS、开放重定向、浏览器扩展。 |
| 04_API、微服务与Web服务安全 | 7 | 服务间与对外接口的安全：REST、GraphQL、gRPC、WebSocket、Web Service（SOAP）、微服务架构安全。 |
| 05_身份认证与会话管理 | 10 | 身份认证与会话全生命周期：认证、口令存储、多因素认证、忘记密码、安全问题、撞库防护、邮箱验证、JAAS、会话管理、Cookie 窃取缓解。 |
| 06_授权与访问控制 | 6 | 授权模型与访问控制实现：通用授权、IDOR、事务授权、多租户隔离，以及授权的自动化测试与回归测试。 |
| 07_令牌、联合身份与密码学 | 6 | 自包含令牌与联邦身份（JWT、SAML、OAuth 2.0／OIDC），以及加密存储、密钥管理、机密信息管理。 |
| 08_传输层、网络与数据保护 | 5 | 传输层与网络层防护（TLS、证书／公钥固定、网络分段），以及数据库安全配置与用户隐私保护。 |
| 09_供应链与依赖安全 | 4 | 软件供应链、SBOM、易受攻击依赖管理，以及 NPM 包管理安全最佳实践。 |
| 10_日志、监控与错误处理 | 3 | 安全日志记录、日志词汇规范、日志保护与错误处理。 |
| 11_业务逻辑与反自动化 | 3 | 业务逻辑缺陷、拒绝服务，以及机器人流量与自动化滥用治理。 |
| 12_编程语言与框架专项 | 11 | 面向具体语言／框架的落地清单；二级目录按技术栈划分。 |
| 13_云原生、容器与基础设施 | 10 | 容器与编排、CI/CD 与基础设施即代码、云架构与零信任；二级目录按平台划分。 |
| 14_AI与LLM应用安全 | 8 | LLM 提示注入、RAG、MCP、AI Agent、AI 模型运维，以及「用 AI 写代码」的安全指南。 |
| 15_移动与嵌入式安全 | 3 | 移动应用、汽车、无人机等终端与嵌入式场景的安全指南。 |
| 00_索引与标准 | 6 | 站点自带的索引页，非指南正文 |

## 4. 完整对照表

「主分类／二级分类」为本库归档位置，其余列为 OWASP 官方索引中的归属（同一篇常归属多个 ASVS 子章节）。机器可读版本见 `manifest.json`。

| # | 文档 | 主分类 | 二级分类 | ASVS 子章节 | Proactive Controls | Top 10 2021 | MASVS | 原始 URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [Abuse Case Cheat Sheet (Historical)](01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V2.1 V2.3 V14.1 V15.1: | C1 | A04 | MASVS-RESILIENCE | https://cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html |
| 2 | [Attack Surface Analysis Cheat Sheet](01_安全需求、架构与治理/Attack_Surface_Analysis_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V15.1: | C1 | A04 | MASVS-PLATFORM MASVS-RESILIENCE | https://cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html |
| 3 | [Legacy Application Management Cheat Sheet](01_安全需求、架构与治理/Legacy_Application_Management_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Legacy_Application_Management_Cheat_Sheet.html |
| 4 | [Microservices based Security Arch Doc Cheat Sheet](01_安全需求、架构与治理/Microservices_based_Security_Arch_Doc_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Microservices_based_Security_Arch_Doc_Cheat_Sheet.html |
| 5 | [Secure Code Review Cheat Sheet](01_安全需求、架构与治理/Secure_Code_Review_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V15.4: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html |
| 6 | [Secure Product Design Cheat Sheet](01_安全需求、架构与治理/Secure_Product_Design_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Secure_Product_Design_Cheat_Sheet.html |
| 7 | [Security Terminology Cheat Sheet](01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V1.1 V6.1 V8.1 V11.1 V15.1: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Security_Terminology_Cheat_Sheet.html |
| 8 | [Secure Integration of Third-Party Payment Gateways Cheat Sheet](01_安全需求、架构与治理/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.html |
| 9 | [Threat Modeling Cheat Sheet](01_安全需求、架构与治理/Threat_Modeling_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V15.1: | C1 | A04 | MASVS-RESILIENCE | https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html |
| 10 | [Virtual Patching Cheat Sheet](01_安全需求、架构与治理/Virtual_Patching_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | V15.2: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Virtual_Patching_Cheat_Sheet.html |
| 11 | [Vulnerability Disclosure Cheat Sheet](01_安全需求、架构与治理/Vulnerability_Disclosure_Cheat_Sheet.md) | 01_安全需求、架构与治理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html |
| 12 | [Bean Validation Cheat Sheet](02_输入验证、注入与文件处理/Bean_Validation_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 | C5 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Bean_Validation_Cheat_Sheet.html |
| 13 | [Cross Site Scripting Prevention Cheat Sheet](02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.1 V1.2 V1.3 | C4 | A03 | — | https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html |
| 14 | [DOM based XSS Prevention Cheat Sheet](02_输入验证、注入与文件处理/DOM_based_XSS_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.3 | C4 | A03 | — | https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html |
| 15 | [Deserialization Cheat Sheet](02_输入验证、注入与文件处理/Deserialization_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.5 | C5 | A08 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html |
| 16 | [File Upload Cheat Sheet](02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V5.1 V5.2 V5.4 | C5 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html |
| 17 | [Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/Injection_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.3 | C4 C5 | A03 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html |
| 18 | [Input Validation Cheat Sheet](02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.3 V2.2 V5.1 V5.2 V5.3 | C5 | — | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html |
| 19 | [LDAP Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/LDAP_Injection_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.3 | C4 | A03 | — | https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html |
| 20 | [Mass Assignment Cheat Sheet](02_输入验证、注入与文件处理/Mass_Assignment_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V15.3: | C5 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html |
| 21 | [NoSQL Security Cheat Sheet](02_输入验证、注入与文件处理/NoSQL_Security_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Security_Cheat_Sheet.html |
| 22 | [OS Command Injection Defense Cheat Sheet](02_输入验证、注入与文件处理/OS_Command_Injection_Defense_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 | C5 | A03 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html |
| 23 | [Prototype Pollution Prevention Cheat Sheet](02_输入验证、注入与文件处理/Prototype_Pollution_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V15.3: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.html |
| 24 | [Query Parameterization Cheat Sheet](02_输入验证、注入与文件处理/Query_Parameterization_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 | C3 | A03 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html |
| 25 | [SQL Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/SQL_Injection_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 | C3 | A03 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html |
| 26 | [Server-Side Request Forgery Prevention Cheat Sheet](02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.3 V1.5 V5.3 V13.1 V13.2 | C5 | A10 | — | https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html |
| 27 | [XML External Entity Prevention Cheat Sheet](02_输入验证、注入与文件处理/XML_External_Entity_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.3 V1.5 | C5 | A05 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html |
| 28 | [XML Security Cheat Sheet](02_输入验证、注入与文件处理/XML_Security_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 V1.5 | — | — | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html |
| 29 | [XSS Filter Evasion Cheat Sheet](02_输入验证、注入与文件处理/XSS_Filter_Evasion_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | — | V1.2 | — | A03 | — | https://cheatsheetseries.owasp.org/cheatsheets/XSS_Filter_Evasion_Cheat_Sheet.html |
| 30 | [AJAX Security Cheat Sheet](03_Web前端与浏览器安全/AJAX_Security_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/AJAX_Security_Cheat_Sheet.html |
| 31 | [Browser Extension Security Vulnerabilities Cheat Sheet](03_Web前端与浏览器安全/Browser_Extension_Vulnerabilities_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V10.7 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Browser_Extension_Vulnerabilities_Cheat_Sheet.html |
| 32 | [Clickjacking Defense Cheat Sheet](03_Web前端与浏览器安全/Clickjacking_Defense_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | — | C2 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html |
| 33 | [Content Security Policy Cheat Sheet](03_Web前端与浏览器安全/Content_Security_Policy_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.1 | — | A03 | — | https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html |
| 34 | [Cross-Site Request Forgery Prevention Cheat Sheet](03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V1.3 V3.1 V3.2 V3.3 V3.4 V3.5 V3.7 V4.1 | C7 | A01 | — | https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html |
| 35 | [DOM Clobbering Prevention Cheat Sheet](03_Web前端与浏览器安全/DOM_Clobbering_Prevention_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.2 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/DOM_Clobbering_Prevention_Cheat_Sheet.html |
| 36 | [HTML5 Security Cheat Sheet](03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.2 V3.4 V3.5 V14.2 V14.3 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html |
| 37 | [HTTP Security Response Headers Cheat Sheet](03_Web前端与浏览器安全/HTTP_Headers_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html |
| 38 | [HTTP Strict Transport Security Cheat Sheet](03_Web前端与浏览器安全/HTTP_Strict_Transport_Security_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.1 V3.4 V3.7 | C8 | A02 | MASVS-NETWORK | https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html |
| 39 | [Securing Cascading Style Sheets Cheat Sheet](03_Web前端与浏览器安全/Securing_Cascading_Style_Sheets_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Securing_Cascading_Style_Sheets_Cheat_Sheet.html |
| 40 | [Third Party JavaScript Management Cheat Sheet](03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.2 V3.6 V3.7 V15.1: V15.2: | — | A06 | — | https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html |
| 41 | [Unvalidated Redirects and Forwards Cheat Sheet](03_Web前端与浏览器安全/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | V3.7 V10.4 V15.3: | C5 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html |
| 42 | [Cross-site leaks Cheat Sheet](03_Web前端与浏览器安全/XS_Leaks_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/XS_Leaks_Cheat_Sheet.html |
| 43 | [GraphQL Cheat Sheet](04_API、微服务与Web服务安全/GraphQL_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V4.3 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html |
| 44 | [Microservices Security Cheat Sheet](04_API、微服务与Web服务安全/Microservices_Security_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V2.2 V11.7 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html |
| 45 | [REST Assessment Cheat Sheet](04_API、微服务与Web服务安全/REST_Assessment_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V4.1 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html |
| 46 | [REST Security Cheat Sheet](04_API、微服务与Web服务安全/REST_Security_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V4.1 V4.2 V9.2 | — | — | MASVS-NETWORK | https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html |
| 47 | [WebSocket Security Cheat Sheet](04_API、微服务与Web服务安全/WebSocket_Security_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V4.4 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html |
| 48 | [Web Service Security Cheat Sheet](04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | V2.2 V4.1 V4.2 | — | — | MASVS-NETWORK | https://cheatsheetseries.owasp.org/cheatsheets/Web_Service_Security_Cheat_Sheet.html |
| 49 | [gRPC Security Cheat Sheet](04_API、微服务与Web服务安全/gRPC_Security_Cheat_Sheet.md) | 04_API、微服务与Web服务安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/gRPC_Security_Cheat_Sheet.html |
| 50 | [Authentication Cheat Sheet](05_身份认证与会话管理/Authentication_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.2 V6.3 V6.5 V6.7 V6.8 | C6 | A07 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html |
| 51 | [Choosing and Using Security Questions Cheat Sheet](05_身份认证与会话管理/Choosing_and_Using_Security_Questions_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.4 | C6 | A07 | — | https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html |
| 52 | [Cookie Theft Mitigation Cheat Sheet](05_身份认证与会话管理/Cookie_Theft_Mitigation_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Cookie_Theft_Mitigation_Cheat_Sheet.html |
| 53 | [Credential Stuffing Prevention Cheat Sheet](05_身份认证与会话管理/Credential_Stuffing_Prevention_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.1 V6.3 | C7 | A07 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html |
| 54 | [Email Validation and Verification in Identity Systems Cheat Sheet](05_身份认证与会话管理/Email_Validation_and_Verification_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html |
| 55 | [Forgot Password Cheat Sheet](05_身份认证与会话管理/Forgot_Password_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.3 V6.4 V6.6 | C6 | A07 | — | https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html |
| 56 | [JAAS Cheat Sheet](05_身份认证与会话管理/JAAS_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | — | C6 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/JAAS_Cheat_Sheet.html |
| 57 | [Multifactor Authentication Cheat Sheet](05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.4 V6.5 V6.6 V6.7 | C6 C7 | A07 | — | https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html |
| 58 | [Password Storage Cheat Sheet](05_身份认证与会话管理/Password_Storage_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V6.5 V11.4 | C6 | A07 | MASVS-STORAGE | https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html |
| 59 | [Session Management Cheat Sheet](05_身份认证与会话管理/Session_Management_Cheat_Sheet.md) | 05_身份认证与会话管理 | — | V3.3 V7: V7.1 V7.2 V7.3 V7.4 V7.5 V7.6 V8.2 V16.2: | C6 | A07 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html |
| 60 | [Authorization Cheat Sheet](06_授权与访问控制/Authorization_Cheat_Sheet.md) | 06_授权与访问控制 | — | V8.1 V8.2 V8.4 V16.3: | — | A01 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html |
| 61 | [Authorization Regression Testing Cheat Sheet](06_授权与访问控制/Authorization_Regression_Testing_Cheat_Sheet.md) | 06_授权与访问控制 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Regression_Testing_Cheat_Sheet.html |
| 62 | [Authorization Testing Automation Cheat Sheet](06_授权与访问控制/Authorization_Testing_Automation_Cheat_Sheet.md) | 06_授权与访问控制 | — | V8.1 | C7 | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation_Cheat_Sheet.html |
| 63 | [Insecure Direct Object Reference Prevention Cheat Sheet](06_授权与访问控制/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.md) | 06_授权与访问控制 | — | V8.2 | C7 | A01 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html |
| 64 | [Multi-Tenant Application Security Cheat Sheet](06_授权与访问控制/Multi_Tenant_Security_Cheat_Sheet.md) | 06_授权与访问控制 | — | V8.4 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html |
| 65 | [Transaction Authorization Cheat Sheet](06_授权与访问控制/Transaction_Authorization_Cheat_Sheet.md) | 06_授权与访问控制 | — | V6.5 V8.3 V15.4: | C7 | A01 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html |
| 66 | [Cryptographic Storage Cheat Sheet](07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V11.1 V11.2 V11.3 V11.5 V13.3 V14.1 | C8 | A02 | MASVS-CRYPTO MASVS-STORAGE | https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html |
| 67 | [JSON Web Token Cheat Sheet](07_令牌、联合身份与密码学/JSON_Web_Token_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V9.1 | C6 | A07 | MASVS-AUTH | https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html |
| 68 | [Key Management Cheat Sheet](07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V11.1 V11.3 V11.7 V13.3 | C8 | A02 | MASVS-CRYPTO | https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html |
| 69 | [OAuth 2.0 Protocol Cheatsheet](07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V10.1 V10.2 V10.3 V10.4 V10.5 V10.6 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html |
| 70 | [SAML Security Cheat Sheet](07_令牌、联合身份与密码学/SAML_Security_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V9.1 | C6 | A07 | — | https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html |
| 71 | [Secrets Management Cheat Sheet](07_令牌、联合身份与密码学/Secrets_Management_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | — | V11.7 | — | A02 | MASVS-STORAGE | https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html |
| 72 | [Database Security Cheat Sheet](08_传输层、网络与数据保护/Database_Security_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html |
| 73 | [Network segmentation Cheat Sheet](08_传输层、网络与数据保护/Network_Segmentation_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Network_Segmentation_Cheat_Sheet.html |
| 74 | [Pinning Cheat Sheet](08_传输层、网络与数据保护/Pinning_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | — | — | C8 | A02 | MASVS-NETWORK | https://cheatsheetseries.owasp.org/cheatsheets/Pinning_Cheat_Sheet.html |
| 75 | [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | — | V3.3 V4.1 V4.4 V10.3 V10.4 V11.6 V12.1 V12.2 V12.3 V17.2 | C8 | A02 | MASVS-NETWORK | https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html |
| 76 | [User Privacy Protection Cheat Sheet](08_传输层、网络与数据保护/User_Privacy_Protection_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | — | V14.1 V14.2 | C8 | — | MASVS-PRIVACY | https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html |
| 77 | [Dependency Graph & SBOM Best Practices Cheat Sheet](09_供应链与依赖安全/Dependency_Graph_SBOM_Cheat_Sheet.md) | 09_供应链与依赖安全 | — | V15.1: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Dependency_Graph_SBOM_Cheat_Sheet.html |
| 78 | [NPM Security best practices](09_供应链与依赖安全/NPM_Security_Cheat_Sheet.md) | 09_供应链与依赖安全 | — | V13.4 | — | A06 | — | https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html |
| 79 | [Software Supply Chain Security](09_供应链与依赖安全/Software_Supply_Chain_Security_Cheat_Sheet.md) | 09_供应链与依赖安全 | — | V15.1: V15.2: | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html |
| 80 | [Vulnerable Dependency Management Cheat Sheet](09_供应链与依赖安全/Vulnerable_Dependency_Management_Cheat_Sheet.md) | 09_供应链与依赖安全 | — | V15.2: | C2 | A06 | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html |
| 81 | [Error Handling Cheat Sheet](10_日志、监控与错误处理/Error_Handling_Cheat_Sheet.md) | 10_日志、监控与错误处理 | — | V16.5: | C10 | — | MASVS-CODE | https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html |
| 82 | [Logging Cheat Sheet](10_日志、监控与错误处理/Logging_Cheat_Sheet.md) | 10_日志、监控与错误处理 | — | V10.7 V16.1: V16.2: V16.3: V16.4: | C9 | A09 | MASVS-CODE MASVS-STORAGE | https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html |
| 83 | [Application Logging Vocabulary Cheat Sheet](10_日志、监控与错误处理/Logging_Vocabulary_Cheat_Sheet.md) | 10_日志、监控与错误处理 | — | V16.1: V16.3: | — | A09 | — | https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html |
| 84 | [Bot Management and Anti-Automation Cheat Sheet](11_业务逻辑与反自动化/Bot_Management_and_Anti-Automation_Cheat_Sheet.md) | 11_业务逻辑与反自动化 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html |
| 85 | [Business Logic Security Cheat Sheet](11_业务逻辑与反自动化/Business_Logic_Security_Cheat_Sheet.md) | 11_业务逻辑与反自动化 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html |
| 86 | [Denial of Service Cheat Sheet](11_业务逻辑与反自动化/Denial_of_Service_Cheat_Sheet.md) | 11_业务逻辑与反自动化 | — | V2.4 | — | A07 A11 | — | https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html |
| 87 | [DotNet Security Cheat Sheet](12_编程语言与框架专项/.NET/DotNet_Security_Cheat_Sheet.md) | 12_编程语言与框架专项 | .NET | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/DotNet_Security_Cheat_Sheet.html |
| 88 | [Next.js Security Cheat Sheet](12_编程语言与框架专项/JavaScript与TypeScript/Nextjs_Security_Cheat_Sheet.md) | 12_编程语言与框架专项 | JavaScript与TypeScript | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Nextjs_Security_Cheat_Sheet.html |
| 89 | [NodeJS Security Cheat Sheet](12_编程语言与框架专项/JavaScript与TypeScript/Nodejs_Security_Cheat_Sheet.md) | 12_编程语言与框架专项 | JavaScript与TypeScript | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html |
| 90 | [C-Based Toolchain Hardening Cheat Sheet](12_编程语言与框架专项/Java与C系/C-Based_Toolchain_Hardening_Cheat_Sheet.md) | 12_编程语言与框架专项 | Java与C系 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/C-Based_Toolchain_Hardening_Cheat_Sheet.html |
| 91 | [Java Security Cheat Sheet](12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md) | 12_编程语言与框架专项 | Java与C系 | V1.2 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Java_Security_Cheat_Sheet.html |
| 92 | [Laravel Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md) | 12_编程语言与框架专项 | PHP与Ruby | V13.4 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html |
| 93 | [PHP Configuration Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/PHP_Configuration_Cheat_Sheet.md) | 12_编程语言与框架专项 | PHP与Ruby | — | C2 | A05 | — | https://cheatsheetseries.owasp.org/cheatsheets/PHP_Configuration_Cheat_Sheet.html |
| 94 | [Ruby on Rails Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Ruby_on_Rails_Cheat_Sheet.md) | 12_编程语言与框架专项 | PHP与Ruby | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Ruby_on_Rails_Cheat_Sheet.html |
| 95 | [Symfony Cheat Sheet](12_编程语言与框架专项/PHP与Ruby/Symfony_Cheat_Sheet.md) | 12_编程语言与框架专项 | PHP与Ruby | V13.4 | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Symfony_Cheat_Sheet.html |
| 96 | [Django REST Framework (DRF) Cheat Sheet](12_编程语言与框架专项/Python/Django_REST_Framework_Cheat_Sheet.md) | 12_编程语言与框架专项 | Python | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Django_REST_Framework_Cheat_Sheet.html |
| 97 | [Django Security Cheat Sheet](12_编程语言与框架专项/Python/Django_Security_Cheat_Sheet.md) | 12_编程语言与框架专项 | Python | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Django_Security_Cheat_Sheet.html |
| 98 | [CI/CD Security Cheat Sheet](13_云原生、容器与基础设施/CI-CD与IaC/CI_CD_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | CI-CD与IaC | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html |
| 99 | [GitHub Actions Security Cheat Sheet](13_云原生、容器与基础设施/CI-CD与IaC/GitHub_Actions_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | CI-CD与IaC | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/GitHub_Actions_Security_Cheat_Sheet.html |
| 100 | [Infrastructure as Code Security Cheatsheet](13_云原生、容器与基础设施/CI-CD与IaC/Infrastructure_as_Code_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | CI-CD与IaC | — | — | A05 | — | https://cheatsheetseries.owasp.org/cheatsheets/Infrastructure_as_Code_Security_Cheat_Sheet.html |
| 101 | [Cloud Architecture Security Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Secure_Cloud_Architecture_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 云架构与零信任 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Secure_Cloud_Architecture_Cheat_Sheet.html |
| 102 | [Serverless / FaaS Security Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Serverless_FaaS_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 云架构与零信任 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Serverless_FaaS_Security_Cheat_Sheet.html |
| 103 | [Subdomain Takeover Prevention Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Subdomain_Takeover_Prevention_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 云架构与零信任 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Subdomain_Takeover_Prevention_Cheat_Sheet.html |
| 104 | [Zero Trust Architecture Cheat Sheet](13_云原生、容器与基础设施/云架构与零信任/Zero_Trust_Architecture_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 云架构与零信任 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Zero_Trust_Architecture_Cheat_Sheet.html |
| 105 | [Docker Security Cheat Sheet](13_云原生、容器与基础设施/容器与编排/Docker_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 容器与编排 | V13.2 | — | A05 | — | https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html |
| 106 | [Kubernetes Security Cheat Sheet](13_云原生、容器与基础设施/容器与编排/Kubernetes_Security_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 容器与编排 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html |
| 107 | [Node.js Docker Cheat Sheet](13_云原生、容器与基础设施/容器与编排/NodeJS_Docker_Cheat_Sheet.md) | 13_云原生、容器与基础设施 | 容器与编排 | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/NodeJS_Docker_Cheat_Sheet.html |
| 108 | [AI-Powered Advertising Systems Security Cheat Sheet](14_AI与LLM应用安全/AI-Powered_Advertising_Systems_Security_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/AI-Powered_Advertising_Systems_Security_Cheat_Sheet.html |
| 109 | [AI Agent Security Cheat Sheet](14_AI与LLM应用安全/AI_Agent_Security_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html |
| 110 | [AML and Sanctions Compliance for AI Agent Payments Cheat Sheet](14_AI与LLM应用安全/AML_Sanctions_AI_Agent_Payments_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/AML_Sanctions_AI_Agent_Payments_Cheat_Sheet.html |
| 111 | [LLM Prompt Injection Prevention Cheat Sheet](14_AI与LLM应用安全/LLM_Prompt_Injection_Prevention_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html |
| 112 | [MCP (Model Context Protocol) Security Cheat Sheet](14_AI与LLM应用安全/MCP_Security_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html |
| 113 | [Retrieval-Augmented Generation (RAG) Security Cheat Sheet](14_AI与LLM应用安全/RAG_Security_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html |
| 114 | [Secure AI/ML Model Ops Cheat Sheet](14_AI与LLM应用安全/Secure_AI_Model_Ops_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Secure_AI_Model_Ops_Cheat_Sheet.html |
| 115 | [Secure Coding with AI Cheat Sheet](14_AI与LLM应用安全/Secure_Coding_with_AI_Cheat_Sheet.md) | 14_AI与LLM应用安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html |
| 116 | [Top 10 Automotive Security Vulnerabilities](15_移动与嵌入式安全/Automotive_Security_Cheat_Sheet.md) | 15_移动与嵌入式安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Automotive_Security_Cheat_Sheet.html |
| 117 | [Drone Security Cheat Sheet](15_移动与嵌入式安全/Drone_Security_Cheat_Sheet.md) | 15_移动与嵌入式安全 | — | — | — | — | — | https://cheatsheetseries.owasp.org/cheatsheets/Drone_Security_Cheat_Sheet.html |
| 118 | [Mobile Application Security Cheat Sheet](15_移动与嵌入式安全/Mobile_Application_Security_Cheat_Sheet.md) | 15_移动与嵌入式安全 | — | — | — | — | MASVS-RESILIENCE | https://cheatsheetseries.owasp.org/cheatsheets/Mobile_Application_Security_Cheat_Sheet.html |

## 5. 被引用最多的文档

统计口径：本库 118 篇正文与 6 个索引页之间的相对链接。

| 文档 | 主分类 | 被引次数 |
| --- | --- | --- |
| [Input Validation Cheat Sheet](02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | 24 |
| [Cross Site Scripting Prevention Cheat Sheet](02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | 22 |
| [Authentication Cheat Sheet](05_身份认证与会话管理/Authentication_Cheat_Sheet.md) | 05_身份认证与会话管理 | 21 |
| [SQL Injection Prevention Cheat Sheet](02_输入验证、注入与文件处理/SQL_Injection_Prevention_Cheat_Sheet.md) | 02_输入验证、注入与文件处理 | 18 |
| [Cryptographic Storage Cheat Sheet](07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | 16 |
| [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) | 08_传输层、网络与数据保护 | 16 |
| [Secrets Management Cheat Sheet](07_令牌、联合身份与密码学/Secrets_Management_Cheat_Sheet.md) | 07_令牌、联合身份与密码学 | 14 |
| [Logging Cheat Sheet](10_日志、监控与错误处理/Logging_Cheat_Sheet.md) | 10_日志、监控与错误处理 | 14 |
| [Cross-Site Request Forgery Prevention Cheat Sheet](03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | 14 |
| [Session Management Cheat Sheet](05_身份认证与会话管理/Session_Management_Cheat_Sheet.md) | 05_身份认证与会话管理 | 13 |
| [Password Storage Cheat Sheet](05_身份认证与会话管理/Password_Storage_Cheat_Sheet.md) | 05_身份认证与会话管理 | 13 |
| [Multifactor Authentication Cheat Sheet](05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md) | 05_身份认证与会话管理 | 13 |
| [Threat Modeling Cheat Sheet](01_安全需求、架构与治理/Threat_Modeling_Cheat_Sheet.md) | 01_安全需求、架构与治理 | 10 |
| [Authorization Cheat Sheet](06_授权与访问控制/Authorization_Cheat_Sheet.md) | 06_授权与访问控制 | 10 |
| [Content Security Policy Cheat Sheet](03_Web前端与浏览器安全/Content_Security_Policy_Cheat_Sheet.md) | 03_Web前端与浏览器安全 | 9 |

从未被其他正文引用的文档（49 篇）。其中多数是技术栈专项、AI 与嵌入式类（彼此独立、只被索引页列出），以及种子文档本身，属正常：

- 01_安全需求、架构与治理/Legacy_Application_Management_Cheat_Sheet.md
- 01_安全需求、架构与治理/Microservices_based_Security_Arch_Doc_Cheat_Sheet.md
- 01_安全需求、架构与治理/Secure_Code_Review_Cheat_Sheet.md
- 01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md
- 01_安全需求、架构与治理/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.md
- 01_安全需求、架构与治理/Virtual_Patching_Cheat_Sheet.md
- 01_安全需求、架构与治理/Vulnerability_Disclosure_Cheat_Sheet.md
- 02_输入验证、注入与文件处理/Bean_Validation_Cheat_Sheet.md
- 02_输入验证、注入与文件处理/Prototype_Pollution_Prevention_Cheat_Sheet.md
- 03_Web前端与浏览器安全/AJAX_Security_Cheat_Sheet.md
- 03_Web前端与浏览器安全/Browser_Extension_Vulnerabilities_Cheat_Sheet.md
- 03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md
- 03_Web前端与浏览器安全/Securing_Cascading_Style_Sheets_Cheat_Sheet.md
- 03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md
- 03_Web前端与浏览器安全/XS_Leaks_Cheat_Sheet.md
- 04_API、微服务与Web服务安全/GraphQL_Cheat_Sheet.md
- 04_API、微服务与Web服务安全/Microservices_Security_Cheat_Sheet.md
- 04_API、微服务与Web服务安全/REST_Assessment_Cheat_Sheet.md
- 04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md
- 04_API、微服务与Web服务安全/gRPC_Security_Cheat_Sheet.md
- 05_身份认证与会话管理/Cookie_Theft_Mitigation_Cheat_Sheet.md
- 05_身份认证与会话管理/Email_Validation_and_Verification_Cheat_Sheet.md
- 05_身份认证与会话管理/JAAS_Cheat_Sheet.md
- 06_授权与访问控制/Authorization_Regression_Testing_Cheat_Sheet.md
- 08_传输层、网络与数据保护/Database_Security_Cheat_Sheet.md
- 08_传输层、网络与数据保护/Network_Segmentation_Cheat_Sheet.md
- 08_传输层、网络与数据保护/User_Privacy_Protection_Cheat_Sheet.md
- 09_供应链与依赖安全/Dependency_Graph_SBOM_Cheat_Sheet.md
- 11_业务逻辑与反自动化/Bot_Management_and_Anti-Automation_Cheat_Sheet.md
- 11_业务逻辑与反自动化/Business_Logic_Security_Cheat_Sheet.md
- 12_编程语言与框架专项/JavaScript与TypeScript/Nextjs_Security_Cheat_Sheet.md
- 12_编程语言与框架专项/Java与C系/C-Based_Toolchain_Hardening_Cheat_Sheet.md
- 12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md
- 12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md
- 12_编程语言与框架专项/PHP与Ruby/Ruby_on_Rails_Cheat_Sheet.md
- 12_编程语言与框架专项/PHP与Ruby/Symfony_Cheat_Sheet.md
- 12_编程语言与框架专项/Python/Django_REST_Framework_Cheat_Sheet.md
- 12_编程语言与框架专项/Python/Django_Security_Cheat_Sheet.md
- 13_云原生、容器与基础设施/CI-CD与IaC/GitHub_Actions_Security_Cheat_Sheet.md
- 13_云原生、容器与基础设施/云架构与零信任/Secure_Cloud_Architecture_Cheat_Sheet.md
- 13_云原生、容器与基础设施/云架构与零信任/Serverless_FaaS_Security_Cheat_Sheet.md
- 13_云原生、容器与基础设施/云架构与零信任/Zero_Trust_Architecture_Cheat_Sheet.md
- 13_云原生、容器与基础设施/容器与编排/NodeJS_Docker_Cheat_Sheet.md
- 14_AI与LLM应用安全/AI-Powered_Advertising_Systems_Security_Cheat_Sheet.md
- 14_AI与LLM应用安全/AML_Sanctions_AI_Agent_Payments_Cheat_Sheet.md
- 14_AI与LLM应用安全/Secure_Coding_with_AI_Cheat_Sheet.md
- 15_移动与嵌入式安全/Automotive_Security_Cheat_Sheet.md
- 15_移动与嵌入式安全/Drone_Security_Cheat_Sheet.md
- 15_移动与嵌入式安全/Mobile_Application_Security_Cheat_Sheet.md

## 6. 排除的文档

抓取到的 122 个候选链接中，以下 4 篇不是指南正文，而是指向新位置的废弃占位页，故不保存：

| 文档 | 抓取到的内容 | 迁移去向 |
| --- | --- | --- |
| Access Control Cheat Sheet | DEPRECATED：正文仅一句废弃声明（约 220 字符） | [Authorization Cheat Sheet](06_授权与访问控制/Authorization_Cheat_Sheet.md) |
| TLS Cipher String Cheat Sheet | DEPRECATED：正文仅一句废弃声明（约 250 字符） | [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) |
| Transport Layer Protection Cheat Sheet | DEPRECATED：正文仅一句废弃声明（约 270 字符） | [Transport Layer Security Cheat Sheet](08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md) |
| Injection Prevention in Java Cheat Sheet | 内容已并入 Java Security（约 230 字符） | [Java Security Cheat Sheet](12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md) |

## 7. 建议阅读顺序

1. 先读 [Secure Code Review Cheat Sheet](01_安全需求、架构与治理/Secure_Code_Review_Cheat_Sheet.md)（种子文档），了解评审方法论与 checklist。
2. 再按 [01_安全需求、架构与治理](01_安全需求、架构与治理/README.md) → [02_输入验证、注入与文件处理](02_输入验证、注入与文件处理/README.md) → [03_Web前端与浏览器安全](03_Web前端与浏览器安全/README.md) 的顺序覆盖通用控制。
3. 之后按技术栈进入 [12_编程语言与框架专项](12_编程语言与框架专项/README.md)、[13_云原生、容器与基础设施](13_云原生、容器与基础设施/README.md)。
4. 需要对齐合规口径时，直接查 `00_索引与标准/` 下的 ASVS／Top 10／Proactive Controls／MASVS 索引。

---

生成时间：2026-09-16 · 内容版权归 OWASP Foundation 所有（CC BY-SA 4.0）
