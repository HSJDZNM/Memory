# 07_令牌、联合身份与密码学

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：自包含令牌与联邦身份（JWT、SAML、OAuth 2.0／OIDC），以及加密存储、密钥管理、机密信息管理。

**文档数**：6

- [Cryptographic Storage Cheat Sheet](Cryptographic_Storage_Cheat_Sheet.md)
  - `ASVS V11.1 V11.2 V11.3 V11.5 V13.3 V14.1 · PC C8 · Top10 A02 · MASVS MASVS-CRYPTO MASVS-STORAGE`
  - This article provides a simple model to follow when implementing solutions to protect data at rest. Passwords should not be stored using reversible encryption - secure password hashing algorithms shou…

- [JSON Web Token Cheat Sheet](JSON_Web_Token_Cheat_Sheet.md)
  - `ASVS V9.1 · PC C6 · Top10 A07 · MASVS MASVS-AUTH`
  - This cheat sheet provides tips to prevent common security issues when using JSON Web Tokens (JWT). JSON Web Tokens (JWT) are security tokens for carrying information (claims), often about a user, an a…

- [Key Management Cheat Sheet](Key_Management_Cheat_Sheet.md)
  - `ASVS V11.1 V11.3 V11.7 V13.3 · PC C8 · Top10 A02 · MASVS MASVS-CRYPTO`
  - This Key Management Cheat Sheet provides developers with guidance for implementation of cryptographic key management within an application in a secure manner. It is important to document and harmonize…

- [OAuth 2.0 Protocol Cheatsheet](OAuth2_Cheat_Sheet.md)
  - `ASVS V10.1 V10.2 V10.3 V10.4 V10.5 V10.6`
  - This cheatsheet describes the best current security practices for OAuth 2.0 as derived from its RFC. OAuth became the standard for API protection and the basis for federated login using OpenID Connect…

- [SAML Security Cheat Sheet](SAML_Security_Cheat_Sheet.md)
  - `ASVS V9.1 · PC C6 · Top10 A07`
  - The S ecurity A ssertion M arkup L anguage (SAML) is an open standard for exchanging authorization and authentication information. The _Web Browser SAML/SSO Profile with Redirect/POST bindings_ is one…

- [Secrets Management Cheat Sheet](Secrets_Management_Cheat_Sheet.md)
  - `ASVS V11.7 · Top10 A02 · MASVS MASVS-STORAGE`
  - Secrets are being used everywhere nowadays, especially with the popularity of the DevOps movement. Application Programming Interface (API) keys, database credentials, Identity and Access Management (I…

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
