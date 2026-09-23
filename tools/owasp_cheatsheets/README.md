# OWASP 代码安全指南库：抓取与归档流水线

从 OWASP Cheat Sheet Series 的 Secure Code Review Cheat Sheet 出发，抓取全部候选指南，
逐篇判定取舍，并按安全领域层级化归档到 `docs/mirrors/owasp-cheatsheets/`。

## 用法

    python tools/owasp_cheatsheets/pipeline.py all     # 全流程
    python tools/owasp_cheatsheets/pipeline.py 03      # 只跑某一阶段

## 阶段

| 脚本 | 作用 | 产出 |
| --- | --- | --- |
| `01_analyze.py` | 解析站点四个索引页，建立交叉引用 | _work/owasp-cheatsheets/taxonomy.json |
| `02_fetch.py` | 抓取 122 篇候选文档 + 6 个索引页 | _work/owasp-cheatsheets/content/、meta.json |
| `03_build.py` | 按层级写入，改写站内链接为相对路径 | docs/mirrors/owasp-cheatsheets/ |
| `04_index.py` | 生成 README / STRUCTURE / manifest / LICENSE，统一换行与编码 | docs/mirrors/owasp-cheatsheets/ |
| `05_verify.py` | 校验链接、编码、换行与 manifest 校验和 | 退出码 |

中间产物位于 `_work/owasp-cheatsheets/`，可随时删除后重跑；`_work/` 不入库。

## 设计说明

**使用纯 HTTP 策略。** 流水线使用 crawl4ai 的 `AsyncHTTPCrawlerStrategy`，不启动浏览器。
Windows 下 asyncio 子进程依赖命名管道，Playwright 驱动在受限沙箱中无法启动
（`PermissionError [WinError 5]`）；目标站点是静态 MkDocs Material 页面，无需 JS 渲染，
与仓库既有的 `tools/mirror_docs.py` 采用同一策略与同一结论。

**不使用 arun_many。** 其调度器在本环境抓取完成后不返回（挂起），
改用 `Semaphore(6)` + `asyncio.gather` 并发调用 `arun()`，并对每个 URL 施加超时。

**正文提取。** 用 `css_selector=article.md-content__inner` 只取正文容器；
否则站点导航侧栏会把全部 122 个链接混进每一篇正文。

**与 mirror_docs.py 的关系。** 该引擎的模型是「本地目录与 URL 路径严格一一对应」，
而本库按任务要求做了主题重排，二者模型不同，故单独成一套流水线；
差异与代价记录在 `docs/mirrors/owasp-cheatsheets/STRUCTURE.md` 第 2 节。

## 文件

| 文件 | 说明 |
| --- | --- |
| `pipeline.py` | 阶段调度入口 |
| `01_analyze.py` … `05_verify.py` | 各阶段脚本 |
| `CC-BY-SA-4.0.txt` | 随库分发的许可全文，由 `04_index.py` 复制为 LICENSE.txt |
