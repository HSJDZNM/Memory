# Memory

开发仓库根目录。

> 当前状态：**空白基线**。仓库已完成 Git 初始化，但尚未绑定技术栈、构建系统或依赖。

## 用途

待补充。（此处填写项目目标、核心问题域与主要使用场景。）

## 目录结构

```
.
├── .editorconfig      # 编辑器统一约定（缩进、换行、编码）
├── .gitattributes     # 换行符与二进制文件规则
├── .gitignore         # 忽略清单（OS / 编辑器 / 依赖 / 构建产物 / 密钥）
├── AGENTS.md          # 面向 AI 编码代理的仓库约定
└── README.md
```

尚未创建源码目录。选定技术栈后再补充 `src/`、测试目录与构建配置。

## 约定

### 提交信息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>
```

常用 type：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`、`build`、`ci`。
主题行使用祈使语气，不超过 72 字符；破坏性变更在正文以 `BREAKING CHANGE:` 说明。

### 分支

主分支为 `main`。功能开发使用 `feat/<topic>`、修复使用 `fix/<topic>`。

### 文本文件

统一使用 UTF-8 编码与 LF 换行（由 `.gitattributes` 强制，不依赖各机器的 `core.autocrlf`）。
提交前请删除行尾空白，文件以单个换行符结尾（由 `.editorconfig` 提示）。
