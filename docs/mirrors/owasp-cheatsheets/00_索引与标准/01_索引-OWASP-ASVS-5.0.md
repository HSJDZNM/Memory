<!--
source: https://cheatsheetseries.owasp.org/IndexASVS.html
fetched: 2026-09-16
kind: site-index
-->

# ASVS Index
## Table of Contents
  * [Objective](01_索引-OWASP-ASVS-5.0.md#objective)
  * [V1: Encoding and Sanitization](01_索引-OWASP-ASVS-5.0.md#v1-encoding-and-sanitization)
    * [V1.1 Encoding and Sanitization Architecture](01_索引-OWASP-ASVS-5.0.md#v11-encoding-and-sanitization-architecture)
    * [V1.2 Injection Prevention](01_索引-OWASP-ASVS-5.0.md#v12-injection-prevention)
    * [V1.3 Sanitization](01_索引-OWASP-ASVS-5.0.md#v13-sanitization)
    * [V1.4 Memory, String, and Unmanaged Code](01_索引-OWASP-ASVS-5.0.md#v14-memory-string-and-unmanaged-code)
    * [V1.5 Safe Deserialization](01_索引-OWASP-ASVS-5.0.md#v15-safe-deserialization)
  * [V2: Validation and Business Logic](01_索引-OWASP-ASVS-5.0.md#v2-validation-and-business-logic)
    * [V2.1 Validation and Business Logic Documentation](01_索引-OWASP-ASVS-5.0.md#v21-validation-and-business-logic-documentation)
    * [V2.2 Input Validation](01_索引-OWASP-ASVS-5.0.md#v22-input-validation)
    * [V2.3 Business Logic Security](01_索引-OWASP-ASVS-5.0.md#v23-business-logic-security)
    * [V2.4 Anti-automation](01_索引-OWASP-ASVS-5.0.md#v24-anti-automation)
  * [V3: Web Frontend Security](01_索引-OWASP-ASVS-5.0.md#v3-web-frontend-security)
    * [V3.1 Web Frontend Security Documentation](01_索引-OWASP-ASVS-5.0.md#v31-web-frontend-security-documentation)
    * [V3.2 Unintended Content Interpretation](01_索引-OWASP-ASVS-5.0.md#v32-unintended-content-interpretation)
    * [V3.3 Cookie Setup](01_索引-OWASP-ASVS-5.0.md#v33-cookie-setup)
    * [V3.4 Browser Security Mechanism Headers](01_索引-OWASP-ASVS-5.0.md#v34-browser-security-mechanism-headers)
    * [V3.5 Browser Origin Separation](01_索引-OWASP-ASVS-5.0.md#v35-browser-origin-separation)
    * [V3.6 External Resource Integrity](01_索引-OWASP-ASVS-5.0.md#v36-external-resource-integrity)
    * [V3.7 Other Browser Security Considerations](01_索引-OWASP-ASVS-5.0.md#v37-other-browser-security-considerations)
  * [V4: API and Web Service](01_索引-OWASP-ASVS-5.0.md#v4-api-and-web-service)
    * [V4.1 Generic Web Service Security](01_索引-OWASP-ASVS-5.0.md#v41-generic-web-service-security)
    * [V4.2 HTTP Message Structure Validation](01_索引-OWASP-ASVS-5.0.md#v42-http-message-structure-validation)
    * [V4.3 GraphQL](01_索引-OWASP-ASVS-5.0.md#v43-graphql)
    * [V4.4 WebSocket](01_索引-OWASP-ASVS-5.0.md#v44-websocket)
  * [V5: File Handling](01_索引-OWASP-ASVS-5.0.md#v5-file-handling)
    * [V5.1 File Handling Documentation](01_索引-OWASP-ASVS-5.0.md#v51-file-handling-documentation)
    * [V5.2 File Upload and Content](01_索引-OWASP-ASVS-5.0.md#v52-file-upload-and-content)
    * [V5.3 File Storage](01_索引-OWASP-ASVS-5.0.md#v53-file-storage)
    * [V5.4 File Download](01_索引-OWASP-ASVS-5.0.md#v54-file-download)
  * [V6: Authentication](01_索引-OWASP-ASVS-5.0.md#v6-authentication)
    * [V6.1 Authentication Documentation](01_索引-OWASP-ASVS-5.0.md#v61-authentication-documentation)
    * [V6.2 Password Security](01_索引-OWASP-ASVS-5.0.md#v62-password-security)
    * [V6.3 General Authentication Security](01_索引-OWASP-ASVS-5.0.md#v63-general-authentication-security)
    * [V6.4 Authentication Factor Lifecycle and Recovery](01_索引-OWASP-ASVS-5.0.md#v64-authentication-factor-lifecycle-and-recovery)
    * [V6.5 General Multi-factor authentication requirements](01_索引-OWASP-ASVS-5.0.md#v65-general-multi-factor-authentication-requirements)
    * [V6.6 Out-of-Band authentication mechanisms](01_索引-OWASP-ASVS-5.0.md#v66-out-of-band-authentication-mechanisms)
    * [V6.7 Cryptographic authentication mechanism](01_索引-OWASP-ASVS-5.0.md#v67-cryptographic-authentication-mechanism)
    * [V6.8 Authentication with an Identity Provider](01_索引-OWASP-ASVS-5.0.md#v68-authentication-with-an-identity-provider)
  * [V7: Session Management](01_索引-OWASP-ASVS-5.0.md#v7-session-management)
    * [V7.1 Session Management Documentation](01_索引-OWASP-ASVS-5.0.md#v71-session-management-documentation)
    * [V7.2 Fundamental Session Management Security](01_索引-OWASP-ASVS-5.0.md#v72-fundamental-session-management-security)
    * [V7.3 Session Timeout](01_索引-OWASP-ASVS-5.0.md#v73-session-timeout)
    * [V7.4 Session Termination](01_索引-OWASP-ASVS-5.0.md#v74-session-termination)
    * [V7.5 Defenses Against Session Abuse](01_索引-OWASP-ASVS-5.0.md#v75-defenses-against-session-abuse)
    * [V7.6 Federated Re-authentication](01_索引-OWASP-ASVS-5.0.md#v76-federated-re-authentication)
  * [V8: Authorization](01_索引-OWASP-ASVS-5.0.md#v8-authorization)
    * [V8.1 Authorization Documentation](01_索引-OWASP-ASVS-5.0.md#v81-authorization-documentation)
    * [V8.2 General Authorization Design](01_索引-OWASP-ASVS-5.0.md#v82-general-authorization-design)
    * [V8.3 Operation Level Authorization](01_索引-OWASP-ASVS-5.0.md#v83-operation-level-authorization)
    * [V8.4 Other Authorization Considerations](01_索引-OWASP-ASVS-5.0.md#v84-other-authorization-considerations)
  * [V9: Self-contained Tokens](01_索引-OWASP-ASVS-5.0.md#v9-self-contained-tokens)
    * [V9.1 Token source and integrity](01_索引-OWASP-ASVS-5.0.md#v91-token-source-and-integrity)
    * [V9.2 Token content](01_索引-OWASP-ASVS-5.0.md#v92-token-content)
  * [V10: OAuth and OIDC](01_索引-OWASP-ASVS-5.0.md#v10-oauth-and-oidc)
    * [V10.1 Generic OAuth and OIDC Security](01_索引-OWASP-ASVS-5.0.md#v101-generic-oauth-and-oidc-security)
    * [V10.2 OAuth Client](01_索引-OWASP-ASVS-5.0.md#v102-oauth-client)
    * [V10.3 OAuth Resource Server](01_索引-OWASP-ASVS-5.0.md#v103-oauth-resource-server)
    * [V10.4 OAuth Authorization Server](01_索引-OWASP-ASVS-5.0.md#v104-oauth-authorization-server)
    * [V10.5 OIDC Client](01_索引-OWASP-ASVS-5.0.md#v105-oidc-client)
    * [V10.6 OpenID Provider](01_索引-OWASP-ASVS-5.0.md#v106-openid-provider)
    * [V10.7 Consent Management](01_索引-OWASP-ASVS-5.0.md#v107-consent-management)
  * [V11: Cryptography](01_索引-OWASP-ASVS-5.0.md#v11-cryptography)
    * [V11.1 Cryptographic Inventory and Documentation](01_索引-OWASP-ASVS-5.0.md#v111-cryptographic-inventory-and-documentation)
    * [V11.2 Secure Cryptography Implementation](01_索引-OWASP-ASVS-5.0.md#v112-secure-cryptography-implementation)
    * [V11.3 Encryption Algorithms](01_索引-OWASP-ASVS-5.0.md#v113-encryption-algorithms)
    * [V11.4 Hashing and Hash-based Functions](01_索引-OWASP-ASVS-5.0.md#v114-hashing-and-hash-based-functions)
    * [V11.5 Random Values](01_索引-OWASP-ASVS-5.0.md#v115-random-values)
    * [V11.6 Public Key Cryptography](01_索引-OWASP-ASVS-5.0.md#v116-public-key-cryptography)
    * [V11.7 In-Use Data Cryptography](01_索引-OWASP-ASVS-5.0.md#v117-in-use-data-cryptography)
  * [V12: Secure Communication](01_索引-OWASP-ASVS-5.0.md#v12-secure-communication)
    * [V12.1 General TLS Security Guidance](01_索引-OWASP-ASVS-5.0.md#v121-general-tls-security-guidance)
    * [V12.2 HTTPS Communication with External Facing Services](01_索引-OWASP-ASVS-5.0.md#v122-https-communication-with-external-facing-services)
    * [V12.3 General Service to Service Communication Security](01_索引-OWASP-ASVS-5.0.md#v123-general-service-to-service-communication-security)
  * [V13: Configuration](01_索引-OWASP-ASVS-5.0.md#v13-configuration)
    * [V13.1 Configuration Documentation](01_索引-OWASP-ASVS-5.0.md#v131-configuration-documentation)
    * [V13.2 Backend Communication Configuration](01_索引-OWASP-ASVS-5.0.md#v132-backend-communication-configuration)
    * [V13.3 Secret Management](01_索引-OWASP-ASVS-5.0.md#v133-secret-management)
    * [V13.4 Unintended Information Leakage](01_索引-OWASP-ASVS-5.0.md#v134-unintended-information-leakage)
  * [V14: Data Protection](01_索引-OWASP-ASVS-5.0.md#v14-data-protection)
    * [V14.1 Data Protection Documentation](01_索引-OWASP-ASVS-5.0.md#v141-data-protection-documentation)
    * [V14.2 General Data Protection](01_索引-OWASP-ASVS-5.0.md#v142-general-data-protection)
    * [V14.3 Client-side Data Protection](01_索引-OWASP-ASVS-5.0.md#v143-client-side-data-protection)
  * [V15: Secure Coding and Architecture](01_索引-OWASP-ASVS-5.0.md#v15-secure-coding-and-architecture)
    * [V15.1: Secure Coding and Architecture Documentation](01_索引-OWASP-ASVS-5.0.md#v151-secure-coding-and-architecture-documentation)
    * [V15.2: Security Architecture and Dependencies](01_索引-OWASP-ASVS-5.0.md#v152-security-architecture-and-dependencies)
    * [V15.3: Defensive Coding](01_索引-OWASP-ASVS-5.0.md#v153-defensive-coding)
    * [V15.4: Safe Concurrency](01_索引-OWASP-ASVS-5.0.md#v154-safe-concurrency)
  * [V16: Security Logging and Error Handling](01_索引-OWASP-ASVS-5.0.md#v16-security-logging-and-error-handling)
    * [V16.1: Security Logging Documentation](01_索引-OWASP-ASVS-5.0.md#v161-security-logging-documentation)
    * [V16.2: General Logging](01_索引-OWASP-ASVS-5.0.md#v162-general-logging)
    * [V16.3: Security Events](01_索引-OWASP-ASVS-5.0.md#v163-security-events)
    * [V16.4: Log Protection](01_索引-OWASP-ASVS-5.0.md#v164-log-protection)
    * [V16.5: Error Handling](01_索引-OWASP-ASVS-5.0.md#v165-error-handling)
  * [V17: WebRTC](01_索引-OWASP-ASVS-5.0.md#v17-webrtc)
    * [V17.1: TURN Server](01_索引-OWASP-ASVS-5.0.md#v171-turn-server)
    * [V17.2: Media](01_索引-OWASP-ASVS-5.0.md#v172-media)
    * [V17.3: Signaling](01_索引-OWASP-ASVS-5.0.md#v173-signaling)


## Objective
The objective of this index is to help an OWASP [Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) (ASVS) user clearly identify which cheat sheets are useful for each section during his or her usage of the ASVS.
This index is based on the version 5.0.x of the ASVS.
## V1: Encoding and Sanitization
### V1.1 Encoding and Sanitization Architecture
[Security Terminology Cheat Sheet](../01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)
[Cross Site Scripting Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md)
### V1.2 Injection Prevention
[Bean Validation Cheat Sheet](../02_输入验证、注入与文件处理/Bean_Validation_Cheat_Sheet.md)
[Cross Site Scripting Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md)
[DOM based XSS Prevention Cheat Sheet](../02_输入验证、注入与文件处理/DOM_based_XSS_Prevention_Cheat_Sheet.md)
[File Upload Cheat Sheet](../02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md)
[Injection Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Injection_Prevention_Cheat_Sheet.md)
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[Java Security Cheat Sheet](../12_编程语言与框架专项/Java与C系/Java_Security_Cheat_Sheet.md)
[LDAP Injection Prevention](../02_输入验证、注入与文件处理/LDAP_Injection_Prevention_Cheat_Sheet.md)
[OS Command Injection Defense](../02_输入验证、注入与文件处理/OS_Command_Injection_Defense_Cheat_Sheet.md)
[Query Parameterization Cheat Sheet](../02_输入验证、注入与文件处理/Query_Parameterization_Cheat_Sheet.md)
[SQL Injection Prevention](../02_输入验证、注入与文件处理/SQL_Injection_Prevention_Cheat_Sheet.md)
[XML Security Cheat Sheet](../02_输入验证、注入与文件处理/XML_Security_Cheat_Sheet.md)
[XSS Filter Evasion Cheat Sheet](../02_输入验证、注入与文件处理/XSS_Filter_Evasion_Cheat_Sheet.md)
[XML External Entity Prevention Cheat Sheet](../02_输入验证、注入与文件处理/XML_External_Entity_Prevention_Cheat_Sheet.md)
### V1.3 Sanitization
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[Cross Site Scripting Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Cross_Site_Scripting_Prevention_Cheat_Sheet.md)
[DOM based XSS Prevention Cheat Sheet](../02_输入验证、注入与文件处理/DOM_based_XSS_Prevention_Cheat_Sheet.md)
[Injection Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Injection_Prevention_Cheat_Sheet.md)
[Injection Prevention Cheat Sheet in Java](https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_in_Java_Cheat_Sheet.html)
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[LDAP Injection Prevention](../02_输入验证、注入与文件处理/LDAP_Injection_Prevention_Cheat_Sheet.md)
[Server Side Request Forgery Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
[XML External Entity Prevention Cheat Sheet](../02_输入验证、注入与文件处理/XML_External_Entity_Prevention_Cheat_Sheet.md)
### V1.4 Memory, String, and Unmanaged Code
None.
### V1.5 Safe Deserialization
[Deserialization Cheat Sheet](../02_输入验证、注入与文件处理/Deserialization_Cheat_Sheet.md)
[Server Side Request Forgery Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
[XML Security Cheat Sheet](../02_输入验证、注入与文件处理/XML_Security_Cheat_Sheet.md)
[XML External Entity Prevention Cheat Sheet](../02_输入验证、注入与文件处理/XML_External_Entity_Prevention_Cheat_Sheet.md)
## V2: Validation and Business Logic
### V2.1 Validation and Business Logic Documentation
[Abuse Case Cheat Sheet](../01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md)
### V2.2 Input Validation
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[Microservices Security Cheat Sheet](../04_API、微服务与Web服务安全/Microservices_Security_Cheat_Sheet.md)
[Web Service Security Cheat Sheet](../04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md)
### V2.3 Business Logic Security
[Abuse Case Cheat Sheet](../01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md)
### V2.4 Anti-automation
[Denial of Service Cheat Sheet](../11_业务逻辑与反自动化/Denial_of_Service_Cheat_Sheet.md)
## V3: Web Frontend Security
### V3.1 Web Frontend Security Documentation
[Content Security Policy Cheat Sheet](../03_Web前端与浏览器安全/Content_Security_Policy_Cheat_Sheet.md)
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[HTTP Strict Transport Security Cheat Sheet](../03_Web前端与浏览器安全/HTTP_Strict_Transport_Security_Cheat_Sheet.md)
### V3.2 Unintended Content Interpretation
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[DOM Clobbering Prevention Cheat Sheet](../03_Web前端与浏览器安全/DOM_Clobbering_Prevention_Cheat_Sheet.md)
[HTML5 Security Cheat Sheet](../03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)
[Third Party Javascript Management Cheat Sheet](../03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)
### V3.3 Cookie Setup
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
### V3.4 Browser Security Mechanism Headers
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[HTML5 Security Cheat Sheet](../03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)
[HTTP Strict Transport Security Cheat Sheet](../03_Web前端与浏览器安全/HTTP_Strict_Transport_Security_Cheat_Sheet.md)
### V3.5 Browser Origin Separation
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[HTML5 Security Cheat Sheet](../03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)
### V3.6 External Resource Integrity
[Third Party Javascript Management Cheat Sheet](../03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)
### V3.7 Other Browser Security Considerations
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[HTTP Strict Transport Security Cheat Sheet](../03_Web前端与浏览器安全/HTTP_Strict_Transport_Security_Cheat_Sheet.md)
[Third Party Javascript Management Cheat Sheet](../03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)
[Unvalidated Redirects and Forwards Cheat Sheet](../03_Web前端与浏览器安全/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
## V4: API and Web Service
### V4.1 Generic Web Service Security
[Cross-Site Request Forgery Prevention Cheat Sheet](../03_Web前端与浏览器安全/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
[REST Assessment Cheat Sheet](../04_API、微服务与Web服务安全/REST_Assessment_Cheat_Sheet.md)
[REST Security Cheat Sheet](../04_API、微服务与Web服务安全/REST_Security_Cheat_Sheet.md)
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
[Web Service Security Cheat Sheet](../04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md)
### V4.2 HTTP Message Structure Validation
[REST Security Cheat Sheet](../04_API、微服务与Web服务安全/REST_Security_Cheat_Sheet.md)
[Web Service Security Cheat Sheet](../04_API、微服务与Web服务安全/Web_Service_Security_Cheat_Sheet.md)
### V4.3 GraphQL
[REST Security Cheat Sheet](../04_API、微服务与Web服务安全/GraphQL_Cheat_Sheet.md)
### V4.4 WebSocket
[REST Security Cheat Sheet](../04_API、微服务与Web服务安全/WebSocket_Security_Cheat_Sheet.md)
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
## V5: File Handling
### V5.1 File Handling Documentation
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[File Upload Cheat Sheet](../02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md)
### V5.2 File Upload and Content
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[File Upload Cheat Sheet](../02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md)
### V5.3 File Storage
[Input Validation Cheat Sheet](../02_输入验证、注入与文件处理/Input_Validation_Cheat_Sheet.md)
[Server Side Request Forgery Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
### V5.4 File Download
[File Upload Cheat Sheet](../02_输入验证、注入与文件处理/File_Upload_Cheat_Sheet.md)
## V6: Authentication
### V6.1 Authentication Documentation
[Security Terminology Cheat Sheet](../01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)
[Credential Stuffing Prevention Cheat Sheet](../05_身份认证与会话管理/Credential_Stuffing_Prevention_Cheat_Sheet.md)
### V6.2 Password Security
[Authentication Cheat Sheet](../05_身份认证与会话管理/Authentication_Cheat_Sheet.md)
### V6.3 General Authentication Security
[Authentication Cheat Sheet](../05_身份认证与会话管理/Authentication_Cheat_Sheet.md)
[Credential Stuffing Prevention Cheat Sheet](../05_身份认证与会话管理/Credential_Stuffing_Prevention_Cheat_Sheet.md)
[Forgot Password Cheat Sheet](../05_身份认证与会话管理/Forgot_Password_Cheat_Sheet.md)
### V6.4 Authentication Factor Lifecycle and Recovery
[Choosing and Using Security Questions Cheat Sheet](../05_身份认证与会话管理/Choosing_and_Using_Security_Questions_Cheat_Sheet.md)
[Forgot Password Cheat Sheet](../05_身份认证与会话管理/Forgot_Password_Cheat_Sheet.md)
[Multifactor Authentication Cheat Sheet](../05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md)
### V6.5 General Multi-factor authentication requirements
[Authentication Cheat Sheet](../05_身份认证与会话管理/Authentication_Cheat_Sheet.md)
[Multifactor Authentication Cheat Sheet](../05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md)
[Password Storage Cheat Sheet](../05_身份认证与会话管理/Password_Storage_Cheat_Sheet.md)
[Transaction Authorization Cheat Sheet](../06_授权与访问控制/Transaction_Authorization_Cheat_Sheet.md)
### V6.6 Out-of-Band authentication mechanisms
[Forgot Password Cheat Sheet](../05_身份认证与会话管理/Forgot_Password_Cheat_Sheet.md)
[Multifactor Authentication Cheat Sheet](../05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md)
### V6.7 Cryptographic authentication mechanism
[Authentication Cheat Sheet](../05_身份认证与会话管理/Authentication_Cheat_Sheet.md)
[Multifactor Authentication Cheat Sheet](../05_身份认证与会话管理/Multifactor_Authentication_Cheat_Sheet.md)
### V6.8 Authentication with an Identity Provider
[Authentication Cheat Sheet](../05_身份认证与会话管理/Authentication_Cheat_Sheet.md)
## V7: Session Management
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.1 Session Management Documentation
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.2 Fundamental Session Management Security
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.3 Session Timeout
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.4 Session Termination
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.5 Defenses Against Session Abuse
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V7.6 Federated Re-authentication
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
## V8: Authorization
### V8.1 Authorization Documentation
[Security Terminology Cheat Sheet](../01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)
[Authorization Cheat Sheet](../06_授权与访问控制/Authorization_Cheat_Sheet.md)
[Authorization Testing Automation](../06_授权与访问控制/Authorization_Testing_Automation_Cheat_Sheet.md)
### V8.2 General Authorization Design
[Authorization Cheat Sheet](../06_授权与访问控制/Authorization_Cheat_Sheet.md)
[Insecure Direct Object Reference Prevention Cheat Sheet](../06_授权与访问控制/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.md)
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V8.3 Operation Level Authorization
[Transaction Authorization Cheat Sheet](../06_授权与访问控制/Transaction_Authorization_Cheat_Sheet.md)
### V8.4 Other Authorization Considerations
[Authorization Cheat Sheet](../06_授权与访问控制/Authorization_Cheat_Sheet.md)
[Multi-Tenant Application Security Cheat Sheet](../06_授权与访问控制/Multi_Tenant_Security_Cheat_Sheet.md)
## V9: Self-contained Tokens
### V9.1 Token source and integrity
[JSON Web Token Cheat Sheet](../07_令牌、联合身份与密码学/JSON_Web_Token_Cheat_Sheet.md)
[SAML Security Cheat Sheet](../07_令牌、联合身份与密码学/SAML_Security_Cheat_Sheet.md)
### V9.2 Token content
[REST Security Cheat Sheet](../04_API、微服务与Web服务安全/REST_Security_Cheat_Sheet.md)
## V10: OAuth and OIDC
### V10.1 Generic OAuth and OIDC Security
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
### V10.2 OAuth Client
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
### V10.3 OAuth Resource Server
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
### V10.4 OAuth Authorization Server
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
[Unvalidated Redirects and Forwards Cheat Sheet](../03_Web前端与浏览器安全/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
### V10.5 OIDC Client
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
### V10.6 OpenID Provider
[OAuth 2.0 Protocol Cheatsheet](../07_令牌、联合身份与密码学/OAuth2_Cheat_Sheet.md)
### V10.7 Consent Management
[Browser Extension Security Vulnerabilities](../03_Web前端与浏览器安全/Browser_Extension_Vulnerabilities_Cheat_Sheet.md)
[Logging Cheat Sheet](../10_日志、监控与错误处理/Logging_Cheat_Sheet.md)
## V11: Cryptography
### V11.1 Cryptographic Inventory and Documentation
[Security Terminology Cheat Sheet](../01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
[Key Management Cheat Sheet](../07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md)
### V11.2 Secure Cryptography Implementation
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
### V11.3 Encryption Algorithms
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
[Key Management Cheat Sheet](../07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md)
### V11.4 Hashing and Hash-based Functions
[Password Storage Cheat Sheet](../05_身份认证与会话管理/Password_Storage_Cheat_Sheet.md)
### V11.5 Random Values
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
### V11.6 Public Key Cryptography
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
### V11.7 In-Use Data Cryptography
[Key Management Cheat Sheet](../07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md)
[Microservices Security Cheat Sheet](../04_API、微服务与Web服务安全/Microservices_Security_Cheat_Sheet.md)
[Secrets Management Cheat Sheet](../07_令牌、联合身份与密码学/Secrets_Management_Cheat_Sheet.md)
## V12: Secure Communication
### V12.1 General TLS Security Guidance
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
### V12.2 HTTPS Communication with External Facing Services
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
### V12.3 General Service to Service Communication Security
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
## V13: Configuration
### V13.1 Configuration Documentation
[Server Side Request Forgery Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
### V13.2 Backend Communication Configuration
[Docker Security Cheat Sheet](../13_云原生、容器与基础设施/容器与编排/Docker_Security_Cheat_Sheet.md)
[Server Side Request Forgery Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md)
### V13.3 Secret Management
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
[Key Management Cheat Sheet](../07_令牌、联合身份与密码学/Key_Management_Cheat_Sheet.md)
### V13.4 Unintended Information Leakage
[Django Cheat Sheet](../12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md)
[GraphQL Cheat Sheet](../12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md)
[Laravel Cheat Sheet](../12_编程语言与框架专项/PHP与Ruby/Laravel_Cheat_Sheet.md)
[NPM Security best practices](../09_供应链与依赖安全/NPM_Security_Cheat_Sheet.md)
[Symfony Cheat Sheet](../12_编程语言与框架专项/PHP与Ruby/Symfony_Cheat_Sheet.md)
## V14: Data Protection
### V14.1 Data Protection Documentation
[Abuse Case Cheat Sheet](../01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md)
[Cryptographic Storage Cheat Sheet](../07_令牌、联合身份与密码学/Cryptographic_Storage_Cheat_Sheet.md)
[User Privacy Protection Cheat Sheet](../08_传输层、网络与数据保护/User_Privacy_Protection_Cheat_Sheet.md)
### V14.2 General Data Protection
[HTML5 Security Cheat Sheet](../03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)
[User Privacy Protection Cheat Sheet](../08_传输层、网络与数据保护/User_Privacy_Protection_Cheat_Sheet.md)
### V14.3 Client-side Data Protection
[HTML5 Security Cheat Sheet](../03_Web前端与浏览器安全/HTML5_Security_Cheat_Sheet.md)
## V15: Secure Coding and Architecture
### V15.1: Secure Coding and Architecture Documentation
[Security Terminology Cheat Sheet](../01_安全需求、架构与治理/Security_Terminology_Cheat_Sheet.md)
[Abuse Case Cheat Sheet](../01_安全需求、架构与治理/Abuse_Case_Cheat_Sheet.md)
[Attack Surface Analysis Cheat Sheet](../01_安全需求、架构与治理/Attack_Surface_Analysis_Cheat_Sheet.md)
[Dependency Graph & SBOM Best Practices Cheat Sheet](../09_供应链与依赖安全/Dependency_Graph_SBOM_Cheat_Sheet.md)
[Software Supply Chain Security](../09_供应链与依赖安全/Software_Supply_Chain_Security_Cheat_Sheet.md)
[Third Party Javascript Management Cheat Sheet](../03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)
[Threat Modeling Cheat Sheet](../01_安全需求、架构与治理/Threat_Modeling_Cheat_Sheet.md)
### V15.2: Security Architecture and Dependencies
[Software Supply Chain Security](../09_供应链与依赖安全/Software_Supply_Chain_Security_Cheat_Sheet.md)
[Third Party Javascript Management Cheat Sheet](../03_Web前端与浏览器安全/Third_Party_Javascript_Management_Cheat_Sheet.md)
[Virtual Patching Cheat Sheet](../01_安全需求、架构与治理/Virtual_Patching_Cheat_Sheet.md)
[Vulnerable Dependency Management Cheat Sheet](../09_供应链与依赖安全/Vulnerable_Dependency_Management_Cheat_Sheet.md)
### V15.3: Defensive Coding
[Mass Assignment Cheat Sheet](../02_输入验证、注入与文件处理/Mass_Assignment_Cheat_Sheet.md)
[Prototype Pollution Prevention Cheat Sheet](../02_输入验证、注入与文件处理/Prototype_Pollution_Prevention_Cheat_Sheet.md)
[Unvalidated Redirects and Forwards Cheat Sheet](../03_Web前端与浏览器安全/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
### V15.4: Safe Concurrency
[Secure Code Review Cheat Sheet](../01_安全需求、架构与治理/Secure_Code_Review_Cheat_Sheet.md)
[Transaction Authorization Cheat Sheet](../06_授权与访问控制/Transaction_Authorization_Cheat_Sheet.md)
## V16: Security Logging and Error Handling
### V16.1: Security Logging Documentation
[Logging Cheat Sheet](../10_日志、监控与错误处理/Logging_Cheat_Sheet.md)
[Logging Vocabulary Cheat Sheet](../10_日志、监控与错误处理/Logging_Vocabulary_Cheat_Sheet.md)
### V16.2: General Logging
[Logging Cheat Sheet](../10_日志、监控与错误处理/Logging_Cheat_Sheet.md)
[Session Management Cheat Sheet](../05_身份认证与会话管理/Session_Management_Cheat_Sheet.md)
### V16.3: Security Events
[Authorization Cheat Sheet](../06_授权与访问控制/Authorization_Cheat_Sheet.md)
[Logging Cheat Sheet](../10_日志、监控与错误处理/Logging_Cheat_Sheet.md)
[Logging Vocabulary Cheat Sheet](../10_日志、监控与错误处理/Logging_Vocabulary_Cheat_Sheet.md)
### V16.4: Log Protection
[Logging Cheat Sheet](../10_日志、监控与错误处理/Logging_Cheat_Sheet.md)
### V16.5: Error Handling
[Error Handling Cheat Sheet](../10_日志、监控与错误处理/Error_Handling_Cheat_Sheet.md)
## V17: WebRTC
### V17.1 TURN Server
None.
## V17.2 Media
[Transport Layer Security Cheat Sheet](../08_传输层、网络与数据保护/Transport_Layer_Security_Cheat_Sheet.md)
## V17.3 Signaling
None.
