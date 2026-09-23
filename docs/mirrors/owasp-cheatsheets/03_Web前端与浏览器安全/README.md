# 03_Web前端与浏览器安全

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：浏览器侧安全控制：CSP、安全响应头、点击劫持、HTML5、DOM 冲突、CSRF、XS-Leaks、CSS 安全、AJAX、第三方 JS 管理、HSTS、开放重定向、浏览器扩展。

**文档数**：13

- [AJAX Security Cheat Sheet](AJAX_Security_Cheat_Sheet.md)
  - `—`
  - This document will provide a starting point for AJAX security and will hopefully be updated and expanded reasonably often to provide more detailed information about specific frameworks and technologie…

- [Browser Extension Security Vulnerabilities Cheat Sheet](Browser_Extension_Vulnerabilities_Cheat_Sheet.md)
  - `ASVS V10.7`
  - Browser extensions sometimes request more permissions than they actually need. This can grant them access to all tabs, browsing history, and even sensitive user data. If an extension is compromised, i…

- [Clickjacking Defense Cheat Sheet](Clickjacking_Defense_Cheat_Sheet.md)
  - `PC C2`
  - This cheat sheet is intended to provide guidance for developers on how to defend against Clickjacking, also known as UI redress attacks. There are three main mechanisms that can be used to defend agai…

- [Content Security Policy Cheat Sheet](Content_Security_Policy_Cheat_Sheet.md)
  - `ASVS V3.1 · Top10 A03`
  - This article brings forth a way to integrate the defense in depth concept to the client-side of web applications. By injecting the Content-Security-Policy (CSP) headers from the server, the browser is…

- [Cross-Site Request Forgery Prevention Cheat Sheet](Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md)
  - `ASVS V1.3 V3.1 V3.2 V3.3 V3.4 V3.5 V3.7 V4.1 · PC C7 · Top10 A01`
  - A Cross-Site Request Forgery (CSRF) attack occurs when a malicious web site, email, blog, instant message, or program tricks an authenticated user's web browser into performing an unwanted action on a…

- [DOM Clobbering Prevention Cheat Sheet](DOM_Clobbering_Prevention_Cheat_Sheet.md)
  - `ASVS V3.2`
  - DOM Clobbering is a type of code-reuse, HTML-only injection attack, where attackers confuse a web application by injecting HTML elements whose id or name attribute matches the name of security-sensiti…

- [HTML5 Security Cheat Sheet](HTML5_Security_Cheat_Sheet.md)
  - `ASVS V3.2 V3.4 V3.5 V14.2 V14.3`
  - The following cheat sheet serves as a guide for implementing HTML 5 in a secure fashion. Web Messaging (also known as Cross Domain Messaging) provides a means of messaging between documents from diffe…

- [HTTP Security Response Headers Cheat Sheet](HTTP_Headers_Cheat_Sheet.md)
  - `—`
  - HTTP Headers are a great booster for web security with easy implementation. Proper HTTP response headers can help prevent security vulnerabilities like Cross-Site Scripting, Clickjacking, Information …

- [HTTP Strict Transport Security Cheat Sheet](HTTP_Strict_Transport_Security_Cheat_Sheet.md)
  - `ASVS V3.1 V3.4 V3.7 · PC C8 · Top10 A02 · MASVS MASVS-NETWORK`
  - HTTP Strict Transport Security (also named HSTS) is an opt-in security enhancement that is specified by a web application through the use of a special response header. Once a supported browser receive…

- [Securing Cascading Style Sheets Cheat Sheet](Securing_Cascading_Style_Sheets_Cheat_Sheet.md)
  - `—`
  - The goal of this CSS (Not XSS, but Cascading Style Sheet) Cheat Sheet is to inform Programmers, Testers, Security Analysts, Front-End Developers and anyone who is interested in Web Application Securit…

- [Third Party JavaScript Management Cheat Sheet](Third_Party_Javascript_Management_Cheat_Sheet.md)
  - `ASVS V3.2 V3.6 V3.7 V15.1: V15.2: · Top10 A06`
  - Tags, aka marketing tags, analytics tags etc. are small bits of JavaScript on a web page. They can also be HTML image elements when JavaScript is disabled. The reason for them is to collect data on th…

- [Unvalidated Redirects and Forwards Cheat Sheet](Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
  - `ASVS V3.7 V10.4 V15.3: · PC C5`
  - Unvalidated redirects and forwards are possible when a web application accepts untrusted input that could cause the web application to redirect the request to a URL contained within untrusted input. B…

- [Cross-site leaks Cheat Sheet](XS_Leaks_Cheat_Sheet.md)
  - `—`
  - This article describes examples of attacks and defenses against cross-site leaks vulnerability (XS Leaks). Since this vulnerability is based on the core mechanism of modern web browsers, it's also cal…

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
