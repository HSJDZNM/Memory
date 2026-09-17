# 13_云原生、容器与基础设施

> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。

**收录范围**：容器与编排、CI/CD 与基础设施即代码、云架构与零信任；二级目录按平台划分。

**文档数**：10

## CI-CD与IaC

- [CI/CD Security Cheat Sheet](CI-CD与IaC/CI_CD_Security_Cheat_Sheet.md)
  - `—`
  - CI/CD pipelines and processes facilitate efficient, repeatable software builds and deployments; as such, they occupy an important role in the modern SDLC. However, given their importance and popularit…

- [GitHub Actions Security Cheat Sheet](CI-CD与IaC/GitHub_Actions_Security_Cheat_Sheet.md)
  - `—`
  - This cheat sheet provides guidance on securing GitHub Actions workflows, primarily for public GitHub repositories. The main goal is to prevent attacker-controlled code execution, which may lead to the…

- [Infrastructure as Code Security Cheatsheet](CI-CD与IaC/Infrastructure_as_Code_Security_Cheat_Sheet.md)
  - `Top10 A05`
  - Infrastructure as code (IaC), also known as software-defined infrastructure, allows the configuration and deployment of infrastructure components faster with consistency by allowing them to be defined…

## 云架构与零信任

- [Cloud Architecture Security Cheat Sheet](云架构与零信任/Secure_Cloud_Architecture_Cheat_Sheet.md)
  - `—`
  - This cheat sheet will discuss common and necessary security patterns to follow when creating and reviewing cloud architectures. Each section will cover a specific security guideline or cloud design de…

- [Serverless / FaaS Security Cheat Sheet](云架构与零信任/Serverless_FaaS_Security_Cheat_Sheet.md)
  - `—`
  - Serverless computing (Functions as a Service — FaaS) platforms such as AWS Lambda, Azure Functions, and Google Cloud Functions simplify application development and scaling. However, the execution mode…

- [Subdomain Takeover Prevention Cheat Sheet](云架构与零信任/Subdomain_Takeover_Prevention_Cheat_Sheet.md)
  - `—`
  - Subdomain takeover is a vulnerability that occurs when a DNS record (typically a CNAME) points to a cloud resource or third-party service that has been deprovisioned or no longer exists. An attacker c…

- [Zero Trust Architecture Cheat Sheet](云架构与零信任/Zero_Trust_Architecture_Cheat_Sheet.md)
  - `—`
  - This cheat sheet will help you implement Zero Trust Architecture (ZTA) in your organization. Zero Trust means "never trust, always verify" - you don't trust anyone or anything by default, even if they…

## 容器与编排

- [Docker Security Cheat Sheet](容器与编排/Docker_Security_Cheat_Sheet.md)
  - `ASVS V13.2 · Top10 A05`
  - Docker is the most popular containerization technology. When used correctly, it can enhance security compared to running applications directly on the host system. However, certain misconfigurations ca…

- [Kubernetes Security Cheat Sheet](容器与编排/Kubernetes_Security_Cheat_Sheet.md)
  - `—`
  - This cheat sheet provides a starting point for securing a Kubernetes cluster. It is divided into the following categories:

- [Node.js Docker Cheat Sheet](容器与编排/NodeJS_Docker_Cheat_Sheet.md)
  - `—`
  - The following cheatsheet provides production-grade guidelines for building optimized and secure Node.js Docker. You’ll find it helpful regardless of the Node.js application you aim to build. This arti…

---

抓取时间：2026-09-16 · 来源：<https://cheatsheetseries.owasp.org/>
