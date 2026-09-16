# AGENTS.md

面向 AI 编码代理的仓库约定。人类贡献者同样可参考。

## 仓库现状

这是一个**刚初始化的空白基线仓库**，尚未绑定技术栈。因此：

- 没有构建、测试、lint 命令可用；
- 没有源码目录、依赖清单或 CI 配置。

**在添加技术栈之前，不要假设任何框架、包管理器或目录布局存在。**先读 `README.md` 与实际的 `git ls-files`，再动手。

## 工作方式

1. **先勘察再改动**：列出目录、读取相关文件，确认事实后再写代码。
2. **保持改动聚焦**：一个提交只做一件事，不顺手重构无关代码。
3. **不要提交密钥**：`.env`、`*.key`、`*.pem`、`secrets/` 已在 `.gitignore` 中忽略。若确实需要示例配置，提交 `.env.example` 且只放占位值。
4. **不要绕过忽略规则**：禁止使用 `git add -f` 强加被忽略的文件。

## 文本文件规范

- 编码 UTF-8，换行 LF（`.gitattributes` 已强制 `eol=lf`，勿手动改回 CRLF）。
- 文件以单个换行符结尾，不留行尾空白。
- 缩进遵循 `.editorconfig`：默认 2 空格，Python 用 4 空格，Makefile 用 Tab。

## 提交信息

采用 Conventional Commits 格式：

```
<type>(<scope>): <subject>
```

`type` 取 `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf` / `build` / `ci`。
主题行祈使语气、不超过 72 字符。破坏性变更在正文写明 `BREAKING CHANGE:`。

示例：`chore: initialize repository`

## 引入新技术栈时需要同步更新

选定语言/框架后，请一次性补齐并在本文件登记：

- 依赖清单与锁文件（提交锁文件）；
- `README.md` 中的安装、构建、测试、运行命令（必须是**实际可执行**的命令，不要写占位符）；
- CI 配置；
- 相应的 `.gitignore` 条目（若 `.gitignore` 中已有 Node/Python 段，直接沿用）。
