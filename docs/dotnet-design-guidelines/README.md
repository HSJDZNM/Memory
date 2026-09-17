# .NET Framework Design Guidelines（本地镜像）

- **来源**：<https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines>
- **抓取时间**：2026-09-16T08:05:08Z
- **抓取工具**：crawl4ai 0.9.3，AsyncHTTPCrawlerStrategy（纯 HTTP 通道，不启动浏览器）
- **页面数**：49
- **许可**：CC BY 4.0（上游文档仓库 dotnet/docs）

本目录是 Microsoft Learn「Framework design guidelines」整章的离线镜像，共 49 篇：章节总览页 1 篇、
章节索引页 7 篇、指南正文 41 篇。页面清单与层级**都取自站点自身的目录接口**（`toc.json`），
本地文件按 URL 末段扁平命名、与站点 URL 路径一一对应，章节层级见 `STRUCTURE.md`；
正文中的镜像内链接已改写为相对路径，可直接离线跳转。

## 目录

| 本地文件 | 标题 | 角色 |
| --- | --- | --- |
| [abstract-class.md](abstract-class.md) | Abstract Class Design | 指南文档 · Abstract class design |
| [abstractions-abstract-types-and-interfaces.md](abstractions-abstract-types-and-interfaces.md) | Abstractions (Abstract Types and Interfaces) | 指南文档 · Abstractions (abstract types and interfaces) |
| [arrays.md](arrays.md) | Arrays (.NET Framework design guidelines) | 指南文档 · Arrays |
| [attributes.md](attributes.md) | Attributes (.NET Framework design guidelines) | 指南文档 · Attributes |
| [base-classes-for-implementing-abstractions.md](base-classes-for-implementing-abstractions.md) | Base Classes for Implementing Abstractions | 指南文档 · Base classes for implementing abstractions |
| [capitalization-conventions.md](capitalization-conventions.md) | Capitalization Conventions | 指南文档 · Capitalization conventions |
| [choosing-between-class-and-struct.md](choosing-between-class-and-struct.md) | Choosing Between Class and Struct | 指南文档 · Choose between class and struct |
| [common-design-patterns.md](common-design-patterns.md) | Common Design Patterns | 章节索引 · Common design patterns |
| [constructor.md](constructor.md) | Constructor Design | 指南文档 · Constructor design |
| [dependency-properties.md](dependency-properties.md) | Dependency Properties | 指南文档 · Dependency properties |
| [designing-for-extensibility.md](designing-for-extensibility.md) | Designing for Extensibility | 章节索引 · Design for extensibility |
| [dispose-pattern.md](dispose-pattern.md) | Dispose Pattern | 指南文档 · Dispose pattern |
| [enum.md](enum.md) | Enum Design | 指南文档 · Enum design |
| [equality-operators.md](equality-operators.md) | Equality Operators | 指南文档 · Equality operators |
| [event.md](event.md) | Event Design | 指南文档 · Event design |
| [events-and-callbacks.md](events-and-callbacks.md) | Events and Callbacks | 指南文档 · Events and callbacks |
| [exception-throwing.md](exception-throwing.md) | Exception Throwing | 指南文档 · Exception throwing |
| [exceptions-and-performance.md](exceptions-and-performance.md) | Exceptions and Performance | 指南文档 · Exceptions and performance |
| [exceptions.md](exceptions.md) | Design Guidelines for Exceptions | 章节索引 · Exception design guidelines |
| [extension-methods.md](extension-methods.md) | Extension Methods | 指南文档 · Extension methods |
| [field.md](field.md) | Field Design | 指南文档 · Field design |
| [general-naming-conventions.md](general-naming-conventions.md) | General Naming Conventions | 指南文档 · General naming conventions |
| [guidelines-for-collections.md](guidelines-for-collections.md) | Guidelines for Collections | 指南文档 · Collections |
| [index.md](index.md) | Framework design guidelines | 站点首页 · Overview |
| [interface.md](interface.md) | Interface Design | 指南文档 · Interface design |
| [member-overloading.md](member-overloading.md) | Member Overloading | 指南文档 · Member overloading |
| [member.md](member.md) | Member Design Guidelines | 章节索引 · Member design guidelines |
| [names-of-assemblies-and-dlls.md](names-of-assemblies-and-dlls.md) | Names of Assemblies and DLLs | 指南文档 · Names of assemblies and DLLs |
| [names-of-classes-structs-and-interfaces.md](names-of-classes-structs-and-interfaces.md) | Names of Classes, Structs, and Interfaces | 指南文档 · Names of classes, structs, and interfaces |
| [names-of-namespaces.md](names-of-namespaces.md) | Names of Namespaces | 指南文档 · Names of namespaces |
| [names-of-type-members.md](names-of-type-members.md) | Names of Type Members | 指南文档 · Names of type members |
| [naming-guidelines.md](naming-guidelines.md) | Naming guidelines | 章节索引 · Naming guidelines |
| [naming-parameters.md](naming-parameters.md) | Naming Parameters | 指南文档 · Naming parameters |
| [naming-resources.md](naming-resources.md) | Naming Resources | 指南文档 · Naming resources |
| [nested-types.md](nested-types.md) | Nested Types | 指南文档 · Nested types |
| [operator-overloads.md](operator-overloads.md) | Operator Overloads | 指南文档 · Operator overloads |
| [parameter-design.md](parameter-design.md) | Parameter Design | 指南文档 · Parameter design |
| [property.md](property.md) | Property Design | 指南文档 · Property design |
| [protected-members.md](protected-members.md) | Protected Members | 指南文档 · Protected members |
| [sealing.md](sealing.md) | Sealing | 指南文档 · Sealing |
| [serialization.md](serialization.md) | Serialization | 指南文档 · Serialization |
| [static-class.md](static-class.md) | Static Class Design | 指南文档 · Static class design |
| [struct.md](struct.md) | Struct Design | 指南文档 · Struct design |
| [system-xml-usage.md](system-xml-usage.md) | System.Xml Usage | 指南文档 · System.Xml usage |
| [type.md](type.md) | Type design guidelines | 章节索引 · Type design guidelines |
| [unsealed-classes.md](unsealed-classes.md) | Unsealed Classes | 指南文档 · Unsealed classes |
| [usage-guidelines.md](usage-guidelines.md) | Usage guidelines | 章节索引 · Usage guidelines |
| [using-standard-exception-types.md](using-standard-exception-types.md) | Using Standard Exception Types | 指南文档 · Use standard exception types |
| [virtual-members.md](virtual-members.md) | Virtual Members | 指南文档 · Virtual members |

## 收录范围与取舍

**已保存**

- **章节总览页 1 篇**：`index.md`（Framework design guidelines），含全章导语与 7 个章节入口；
- **章节索引页 7 篇**：naming-guidelines、type、member、designing-for-extensibility、exceptions、
  usage-guidelines、common-design-patterns——这 7 个目录节点本身也是页面，含该章导语与子页清单；
- **指南正文 41 篇**：命名规范 8 篇、类型设计 7 篇、成员设计 8 篇、可扩展性设计 7 篇、
  异常设计 3 篇、用法指南 6 篇、常用设计模式 2 篇；
- `manifest.json`：逐页记录来源 URL、本地路径、层级（toc_path / parent / toc_order / chapter）、
  角色与收录理由（role / why）、上游 Markdown 源文件路径、字节数与 sha256，便于校验。

**未保存（及原因）**

- **`dotnet/api/...` API 参考页 163 处引用**：正文提到类型或成员时给出的签名页，
  不属于设计指南章节，且数量随正文引用无限扩张；
- **其他 .NET 文档集的链接 10 处**：`/dotnet/standard/` 8 处（垃圾回收等）、`/dotnet/csharp/` 1 处（装箱拆箱）、`/visualstudio/ide/` 1 处（EditorConfig 命名约定）；
- **原书购买链接 91 处**（www.informit.com）：正文许可声明中指向《Framework Design Guidelines》第 2/3 版书籍页；
- **站点模板链接**（每页「编辑此文档」的 49 条 github 源文件链接、页脚浏览器兼容提示与 Edge 下载链接）：
  在正文净化阶段随模板一并剥离，不进入正文，也不产生本地文件。

## 已知事实

- 抓取期间 49 个页面全部返回 HTTP 200，无失败页；清单与层级来自站点目录接口 `toc.json`，
  而非逐边 BFS；抓取后把每篇正文的全部超链接与该目录比对，站内链接集合与目录完全一致；
- 该站 canonical URL 不带尾斜杠，`.../names-of-namespaces` 与 `.../names-of-namespaces/` 是同一页，
  已在链接映射中等价处理，不会重复收录；
- 正文链接在源站 HTML 里是相对地址（根相对 `/en-us/...` 与同级相对两种），站点模块先按当前页
  URL 解析为绝对地址再交给引擎改写：145 条镜像内链接改写为相对路径，285 条范围外链接保留绝对地址；
- 页面模板把导航、目录侧栏、面包屑与授权提示都放在 `<main>` 内，站点模块先摘除这些模板块，
  否则转换出的 Markdown 会混入大量导航文本；正文末尾的 `Additional resources` 页脚同样被截断；
- 每篇正文末尾保留页面自身标注的更新日期（`_源站标注：Last updated on YYYY-MM-DD_`）；
- 正文摘自 2008 年出版的《Framework Design Guidelines》第 2 版，页面自身声明部分内容可能已经过时，
  并给出第 3 版的购买链接（该链接保留在正文中，未收录为本地文件）；
- 许可分层：上游仓库 `dotnet/docs` 的文档部分为 CC BY 4.0（代码示例为 MIT），
  而本套正文页另含 Pearson Education 授权摘录声明与 Microsoft 版权声明，转载时请连同这些声明一并处理。
