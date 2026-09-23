---
title: "Well-being"
source_url: "https://dora.dev/capabilities/well-being/"
section: "core"
role: "能力文档 · DORA Core 模型"
why: "站点能力目录页给出的模型徽章为 core（/research/#core-model），据此归入 core/"
copyright: "CC BY 4.0（Google LLC；站点页脚声明：除另有说明外，本站内容按 CC BY 4.0 授权）"
fetched_at: "2026-09-17T07:23:13Z"
---

# Well-being

Well-being is a reflection of individuals’ happiness and job satisfaction. Increased well-being predicts organizational performance and employees’ job tenure. DORA has studied the impact of deployment pain, rework, and burnout on well-being.

## Deployment pain

Deployment pain is a measure of the fear and anxiety that engineers and technical staff feel when they push code into production. It also measures the extent to which deployments are disruptive rather than easy and pain-free. Where deployments are most painful, you’ll find the poorest software delivery performance, organizational performance, and organizational culture.

Teams can reduce deployment pain by implementing the technical practices that drive [continuous delivery](continuous-delivery.md). Put another way, the technical practices that improve our ability to deliver software with both speed and stability also reduce the stress and anxiety associated with pushing code into production.

## Rework

One measure of whether teams are building quality into their work is the how they spend their time. Are they able to focus their time devoting effort and energy on developing new features and supporting infrastructure? Or do teams spend most of their time correcting problems, remediating issues, and responding to defects and customer-support work (that is, fixing issues that arise because quality was not built in up front)? We conceptualize this time into two categories. The first category is proactive or new work, in which we are able to design, create, and work on features, tests, and infrastructure in a structured and productive way to create value for our organizations.

The second category is called reactive unplanned work, or rework. Unplanned work includes any break/fix work, emergency software deployments and patches, responding to urgent audit documentation requests, and so on. Rework is fixing things that weren’t done right the first time and, like change fail rate, is a proxy measure for quality.

In the [2016 State of DevOps survey](https://dora.dev/research/2016/2016-state-of-devops-report.pdf), we asked people about the percentage of time they spent on rework and unplanned work, and on new work such as designing and building new features. High performers reported spending 49 percent of their time on new work and 21 percent on unplanned work or rework. By contrast, low performers spend 38 percent of their time on new work and 27 percent on unplanned work or rework. Thus, high performers spend 29 percent more time on new work than low performers, and 22 percent less time on unplanned work and rework.

[Continuous delivery](continuous-delivery.md) predicts lower levels of unplanned work and rework in a statistically significant way, showing that implementing the technical practices behind continuous delivery drives higher quality.

In the [2018 Accelerate State of DevOps survey](https://dora.dev/research/2018/dora-report/2018-dora-accelerate-state-of-devops-report.pdf), we asked our respondents how they spend their time and found that across the board, elite performers are getting the most value-add time out of their days and are spending the least amount of time doing non-value-add work of all groups, followed by high performers and medium performers. Low performers are doing the worst on all dimensions in terms of value-add vs. non-value-add time, as shown in the table below.

| Time spent | Elite | High | Medium | Low |
| --- | --- | --- | --- | --- |
| New work | 50% | 50% | 40% | 30% |
| Unplanned work and rework | 19.5% | 20% | 20% | 20% |
| Remediating security issues | 5% | 5% | 5% | 10% |
| Working on defects identified by end users | 10% | 10% | 10% | 20% |
| Customer support work | 5% | 10% | 10% | 15% |

## Burnout

Burnout is physical, mental, or emotional exhaustion caused by overwork or stress. But it’s more than just being overworked or stressed. Burnout can make the things we once loved about our work and life seem insignificant and dull. It often manifests itself as a feeling of helplessness, and is correlated with pathological cultures and unproductive, wasteful work. Dr Christina Maslach, professor of psychology at the University of California at Berkeley and [a pioneering researcher on job burnout](https://www.ncbi.nlm.nih.gov/pubmed/18457483), found six organizational risk factors that predict burnout:

  * **Work overload**. Job demands that exceed human limits.
  * **Lack of control**. Inability to influence decisions that affect your job.
  * **Insufficient rewards**. Insufficient financial, institutional, or social rewards.
  * **Breakdown of community**. Unsupportive workplace environment.
  * **Absence of fairness**. Lack of fairness in decision-making processes.
  * **Value conflicts**. Mismatch in organizational values and the individual’s values.

Maslach found that most organizations try to fix the person and ignore the work environment, even though data shows that fixing the environment has a higher likelihood of success. Management has the power to change all of these risk factors.
