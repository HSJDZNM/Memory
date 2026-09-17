# 05_身份认证与会话管理

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：身份认证与会话全生命周期：认证、口令存储、多因素认证、忘记密码、安全问题、撞库防护、邮箱验证、JAAS、会话管理、Cookie 窃取缓解。

**文档数**：10

- [Authentication Cheat Sheet](Authentication_Cheat_Sheet.md)
  - `ASVS V6.2 V6.3 V6.5 V6.7 V6.8 · PC C6 · Top10 A07 · MASVS MASVS-AUTH`
  - The primary function of a User ID is to uniquely identify a user within a system. Ideally, User IDs should be randomly generated to prevent the creation of predictable or sequential IDs, which could p…

- [Choosing and Using Security Questions Cheat Sheet](Choosing_and_Using_Security_Questions_Cheat_Sheet.md)
  - `ASVS V6.4 · PC C6 · Top10 A07`
  - If you are curious, please have a look at this study by Microsoft Research in 2009 and this study performed at Google in 2015. The accompanying Security blog update includes an infographic on the issu…

- [Cookie Theft Mitigation Cheat Sheet](Cookie_Theft_Mitigation_Cheat_Sheet.md)
  - `—`
  - With the spread of 2FA and Passkey, the login process has become more robust, and even if an attacker steals only the password, it has become difficult to do a spoofing attack. However, if attacker ca…

- [Credential Stuffing Prevention Cheat Sheet](Credential_Stuffing_Prevention_Cheat_Sheet.md)
  - `ASVS V6.1 V6.3 · PC C7 · Top10 A07 · MASVS MASVS-AUTH`
  - This cheatsheet covers defenses against two common types of authentication-related attacks: credential stuffing and password spraying. Although these are separate, distinct attacks, in many cases the …

- [Email Validation and Verification in Identity Systems Cheat Sheet](Email_Validation_and_Verification_Cheat_Sheet.md)
  - `—`
  - Email addresses are widely used as primary identifiers in authentication and account recovery workflows. Improper handling of email validation, normalization, and verification can lead to account take…

- [Forgot Password Cheat Sheet](Forgot_Password_Cheat_Sheet.md)
  - `ASVS V6.3 V6.4 V6.6 · PC C6 · Top10 A07`
  - In order to implement a proper user management system, systems integrate a Forgot Password service that allows the user to request a password reset. Even though this functionality looks straightforwar…

- [JAAS Cheat Sheet](JAAS_Cheat_Sheet.md)
  - `PC C6`
  - The process of verifying the identity of a user or another system is authentication. JAAS, as an authentication framework manages the authenticated user's identity and credentials from login to logout…

- [Multifactor Authentication Cheat Sheet](Multifactor_Authentication_Cheat_Sheet.md)
  - `ASVS V6.4 V6.5 V6.6 V6.7 · PC C6 C7 · Top10 A07`
  - Multifactor Authentication (MFA) or Two-Factor Authentication (2FA) is when a user is required to present more than one type of evidence in order to authenticate on a system. There are five different …

- [Password Storage Cheat Sheet](Password_Storage_Cheat_Sheet.md)
  - `ASVS V6.5 V11.4 · PC C6 · Top10 A07 · MASVS MASVS-STORAGE`
  - This cheat sheet advises you on the proper methods for storing passwords for authentication. When passwords are stored, they must be protected from an attacker even if the application or database is c…

- [Session Management Cheat Sheet](Session_Management_Cheat_Sheet.md)
  - `ASVS V3.3 V7: V7.1 V7.2 V7.3 V7.4 V7.5 V7.6 V8.2 V16.2: · PC C6 · Top10 A07 · MASVS MASVS-AUTH`
  - A web session is a sequence of network HTTP request and response transactions associated with the same user. Modern and complex web applications require the retaining of information or status about ea…

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
