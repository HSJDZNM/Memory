# 文档关系与层级

本文件说明镜像内 49 篇文档的归属与相互关系。结论均由站点自身的
索引页声明、sitemap 清单与正文实际链接推导得出，不含人工臆测。
## 1. 范围判定

**清单与层级都取自站点自身的目录接口** `https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/toc.json`：该接口给出 49 个带 href 的目录节点——章节总览页 1 篇、章节索引页 7 篇、指南正文 41 篇。
本镜像按这份目录逐页抓取，不依赖逐边 BFS；抓取后再把每篇正文里的全部超链接与目录接口比对，
站内链接集合与目录完全一致，说明本指南之外没有遗漏页面，范围封闭可复核。

**本地路径与层级的关系**：该站 canonical URL 不带尾斜杠（`.../design-guidelines/names-of-namespaces`），
故本地文件按 URL 末段扁平命名（`names-of-namespaces.md`），与站点 URL 路径一一对应；
章节层级由下面的层级树与 `manifest.json` 的 `toc_path` / `parent` / `toc_order` / `chapter` 字段表达，
每篇 front matter 的 `role` 与 `why` 亦标明所属章节。

**层级树**（左侧为本地文件，右侧为上游目录标题）：

```
└── [章节总标题]                                                # Framework design guidelines（目录节点，本身无页面）
    ├── index.md                                           # Overview
    ├── naming-guidelines.md                               # Naming guidelines（章节索引 · 8 篇）
    │   ├── capitalization-conventions.md                  # Capitalization conventions
    │   ├── general-naming-conventions.md                  # General naming conventions
    │   ├── names-of-assemblies-and-dlls.md                # Names of assemblies and DLLs
    │   ├── names-of-namespaces.md                         # Names of namespaces
    │   ├── names-of-classes-structs-and-interfaces.md     # Names of classes, structs, and interfaces
    │   ├── names-of-type-members.md                       # Names of type members
    │   ├── naming-parameters.md                           # Naming parameters
    │   └── naming-resources.md                            # Naming resources
    ├── type.md                                            # Type design guidelines（章节索引 · 7 篇）
    │   ├── choosing-between-class-and-struct.md           # Choose between class and struct
    │   ├── abstract-class.md                              # Abstract class design
    │   ├── static-class.md                                # Static class design
    │   ├── interface.md                                   # Interface design
    │   ├── struct.md                                      # Struct design
    │   ├── enum.md                                        # Enum design
    │   └── nested-types.md                                # Nested types
    ├── member.md                                          # Member design guidelines（章节索引 · 8 篇）
    │   ├── member-overloading.md                          # Member overloading
    │   ├── property.md                                    # Property design
    │   ├── constructor.md                                 # Constructor design
    │   ├── event.md                                       # Event design
    │   ├── field.md                                       # Field design
    │   ├── extension-methods.md                           # Extension methods
    │   ├── operator-overloads.md                          # Operator overloads
    │   └── parameter-design.md                            # Parameter design
    ├── designing-for-extensibility.md                     # Design for extensibility（章节索引 · 7 篇）
    │   ├── unsealed-classes.md                            # Unsealed classes
    │   ├── protected-members.md                           # Protected members
    │   ├── events-and-callbacks.md                        # Events and callbacks
    │   ├── virtual-members.md                             # Virtual members
    │   ├── abstractions-abstract-types-and-interfaces.md  # Abstractions (abstract types and interfaces)
    │   ├── base-classes-for-implementing-abstractions.md  # Base classes for implementing abstractions
    │   └── sealing.md                                     # Sealing
    ├── exceptions.md                                      # Exception design guidelines（章节索引 · 3 篇）
    │   ├── exception-throwing.md                          # Exception throwing
    │   ├── using-standard-exception-types.md              # Use standard exception types
    │   └── exceptions-and-performance.md                  # Exceptions and performance
    ├── usage-guidelines.md                                # Usage guidelines（章节索引 · 6 篇）
    │   ├── arrays.md                                      # Arrays
    │   ├── attributes.md                                  # Attributes
    │   ├── guidelines-for-collections.md                  # Collections
    │   ├── serialization.md                               # Serialization
    │   ├── system-xml-usage.md                            # System.Xml usage
    │   └── equality-operators.md                          # Equality operators
    └── common-design-patterns.md                          # Common design patterns（章节索引 · 2 篇）
        ├── dependency-properties.md                       # Dependency properties
        └── dispose-pattern.md                             # Dispose pattern
```

## 2. 层级结构

```
├── abstract-class.md                              # Abstract Class Design
├── abstractions-abstract-types-and-interfaces.md  # Abstractions (Abstract Types and Interfaces)
├── arrays.md                                      # Arrays (.NET Framework design guidelines)
├── attributes.md                                  # Attributes (.NET Framework design guidelines)
├── base-classes-for-implementing-abstractions.md  # Base Classes for Implementing Abstractions
├── capitalization-conventions.md                  # Capitalization Conventions
├── choosing-between-class-and-struct.md           # Choosing Between Class and Struct
├── common-design-patterns.md                      # Common Design Patterns
├── constructor.md                                 # Constructor Design
├── dependency-properties.md                       # Dependency Properties
├── designing-for-extensibility.md                 # Designing for Extensibility
├── dispose-pattern.md                             # Dispose Pattern
├── enum.md                                        # Enum Design
├── equality-operators.md                          # Equality Operators
├── event.md                                       # Event Design
├── events-and-callbacks.md                        # Events and Callbacks
├── exception-throwing.md                          # Exception Throwing
├── exceptions-and-performance.md                  # Exceptions and Performance
├── exceptions.md                                  # Design Guidelines for Exceptions
├── extension-methods.md                           # Extension Methods
├── field.md                                       # Field Design
├── general-naming-conventions.md                  # General Naming Conventions
├── guidelines-for-collections.md                  # Guidelines for Collections
├── index.md                                       # Framework design guidelines
├── interface.md                                   # Interface Design
├── member-overloading.md                          # Member Overloading
├── member.md                                      # Member Design Guidelines
├── names-of-assemblies-and-dlls.md                # Names of Assemblies and DLLs
├── names-of-classes-structs-and-interfaces.md     # Names of Classes, Structs, and Interfaces
├── names-of-namespaces.md                         # Names of Namespaces
├── names-of-type-members.md                       # Names of Type Members
├── naming-guidelines.md                           # Naming guidelines
├── naming-parameters.md                           # Naming Parameters
├── naming-resources.md                            # Naming Resources
├── nested-types.md                                # Nested Types
├── operator-overloads.md                          # Operator Overloads
├── parameter-design.md                            # Parameter Design
├── property.md                                    # Property Design
├── protected-members.md                           # Protected Members
├── sealing.md                                     # Sealing
├── serialization.md                               # Serialization
├── static-class.md                                # Static Class Design
├── struct.md                                      # Struct Design
├── system-xml-usage.md                            # System.Xml Usage
├── type.md                                        # Type design guidelines
├── unsealed-classes.md                            # Unsealed Classes
├── usage-guidelines.md                            # Usage guidelines
├── using-standard-exception-types.md              # Using Standard Exception Types
└── virtual-members.md                             # Virtual Members
```

本地路径按 canonical URL 末段扁平命名（已剥离 `/en-us/dotnet/standard/design-guidelines/` 范围前缀），
因此任意文件都能反查回其线上地址；章节层级见上方「范围判定」中的层级树与 `manifest.json` 的 `toc_path` 字段。
## 3. 各文档正文大纲（h1–h2）

仅列到二级标题；三级及以下标题见各文件正文自身。

### [Abstract Class Design](abstract-class.md)

```
h1  Abstract Class Design
  h2  See also
```

### [Abstractions (Abstract Types and Interfaces)](abstractions-abstract-types-and-interfaces.md)

```
h1  Abstractions (Abstract Types and Interfaces)
  h2  See also
```

### [Arrays (.NET Framework design guidelines)](arrays.md)

```
h1  Arrays (.NET Framework design guidelines)
  h2  See also
```

### [Attributes (.NET Framework design guidelines)](attributes.md)

```
h1  Attributes (.NET Framework design guidelines)
  h2  See also
```

### [Base Classes for Implementing Abstractions](base-classes-for-implementing-abstractions.md)

```
h1  Base Classes for Implementing Abstractions
  h2  See also
```

### [Capitalization Conventions](capitalization-conventions.md)

```
h1  Capitalization Conventions
  h2  Capitalization Rules for Identifiers
  h2  Capitalizing Compound Words and Common Terms
  h2  Case Sensitivity
  h2  See also
```

### [Choosing Between Class and Struct](choosing-between-class-and-struct.md)

```
h1  Choosing Between Class and Struct
  h2  See also
```

### [Common Design Patterns](common-design-patterns.md)

```
h1  Common Design Patterns
  h2  In This Section
  h2  See also
```

### [Constructor Design](constructor.md)

```
h1  Constructor Design
  h2  Type Constructor Guidelines
  h2  See also
```

### [Dependency Properties](dependency-properties.md)

```
h1  Dependency Properties
  h2  Dependency Property Design
  h2  Attached Dependency Property Design
  h2  Dependency Property Validation
  h2  Dependency Property Change Notifications
  h2  Dependency Property Value Coercion
  h2  See also
```

### [Designing for Extensibility](designing-for-extensibility.md)

```
h1  Designing for Extensibility
  h2  In This Section
  h2  See also
```

### [Dispose Pattern](dispose-pattern.md)

```
h1  Dispose Pattern
  h2  Basic Dispose Pattern
  h2  Finalizable Types
  h2  See also
```

### [Enum Design](enum.md)

```
h1  Enum Design
  h2  See also
```

### [Equality Operators](equality-operators.md)

```
h1  Equality Operators
  h2  Equality Operators on Value Types
  h2  Equality Operators on Reference Types
  h2  See also
```

### [Event Design](event.md)

```
h1  Event Design
  h2  See also
```

### [Events and Callbacks](events-and-callbacks.md)

```
h1  Events and Callbacks
  h2  See also
```

### [Exception Throwing](exception-throwing.md)

```
h1  Exception Throwing
  h2  See also
```

### [Exceptions and Performance](exceptions-and-performance.md)

```
h1  Exceptions and Performance
  h2  Tester-Doer Pattern
  h2  Try-Parse Pattern
  h2  See also
```

### [Design Guidelines for Exceptions](exceptions.md)

```
h1  Design Guidelines for Exceptions
  h2  In This Section
  h2  See also
```

### [Extension Methods](extension-methods.md)

```
h1  Extension Methods
  h2  See also
```

### [Field Design](field.md)

```
h1  Field Design
  h2  See also
```

### [General Naming Conventions](general-naming-conventions.md)

```
h1  General Naming Conventions
  h2  Word Choice
  h2  Using Abbreviations and Acronyms
  h2  Avoiding Language-Specific Names
  h2  Naming New Versions of Existing APIs
  h2  See also
```

### [Guidelines for Collections](guidelines-for-collections.md)

```
h1  Guidelines for Collections
  h2  Collection Parameters
  h2  Collection Properties and Return Values
  h2  Choosing Between Arrays and Collections
  h2  Implementing Custom Collections
  h2  See also
```

### [Framework design guidelines](index.md)

```
h1  Framework design guidelines
  h2  In this section
```

### [Interface Design](interface.md)

```
h1  Interface Design
  h2  See also
```

### [Member Overloading](member-overloading.md)

```
h1  Member Overloading
  h2  See also
```

### [Member Design Guidelines](member.md)

```
h1  Member Design Guidelines
  h2  In This Section
  h2  See also
```

### [Names of Assemblies and DLLs](names-of-assemblies-and-dlls.md)

```
h1  Names of Assemblies and DLLs
  h2  See also
```

### [Names of Classes, Structs, and Interfaces](names-of-classes-structs-and-interfaces.md)

```
h1  Names of Classes, Structs, and Interfaces
  h2  Names of Generic Type Parameters
  h2  Names of Common Types
  h2  Naming Enumerations
  h2  See also
```

### [Names of Namespaces](names-of-namespaces.md)

```
h1  Names of Namespaces
  h2  See also
```

### [Names of Type Members](names-of-type-members.md)

```
h1  Names of Type Members
  h2  Names of Methods
  h2  Names of Properties
  h2  Names of Events
  h2  Names of Fields
  h2  See also
```

### [Naming guidelines](naming-guidelines.md)

```
h1  Naming guidelines
  h2  In this section
  h2  See also
```

### [Naming Parameters](naming-parameters.md)

```
h1  Naming Parameters
  h2  See also
```

### [Naming Resources](naming-resources.md)

```
h1  Naming Resources
  h2  See also
```

### [Nested Types](nested-types.md)

```
h1  Nested Types
  h2  See also
```

### [Operator Overloads](operator-overloads.md)

```
h1  Operator Overloads
  h2  See also
```

### [Parameter Design](parameter-design.md)

```
h1  Parameter Design
  h2  See also
```

### [Property Design](property.md)

```
h1  Property Design
  h2  See also
```

### [Protected Members](protected-members.md)

```
h1  Protected Members
  h2  See also
```

### [Sealing](sealing.md)

```
h1  Sealing
  h2  See also
```

### [Serialization](serialization.md)

```
h1  Serialization
  h2  Choosing the Right Serialization Technology to Support
  h2  Supporting Data Contract Serialization
  h2  Supporting XML Serialization
  h2  Supporting Runtime Serialization
  h2  See also
```

### [Static Class Design](static-class.md)

```
h1  Static Class Design
  h2  See also
```

### [Struct Design](struct.md)

```
h1  Struct Design
  h2  See also
```

### [System.Xml Usage](system-xml-usage.md)

```
h1  System.Xml Usage
  h2  See also
```

### [Type design guidelines](type.md)

```
h1  Type design guidelines
  h2  In this section
  h2  See also
```

### [Unsealed Classes](unsealed-classes.md)

```
h1  Unsealed Classes
  h2  See also
```

### [Usage guidelines](usage-guidelines.md)

```
h1  Usage guidelines
  h2  In this section
  h2  See also
```

### [Using Standard Exception Types](using-standard-exception-types.md)

```
h1  Using Standard Exception Types
  h2  Exception and SystemException
  h2  ApplicationException
  h2  InvalidOperationException
  h2  ArgumentException, ArgumentNullException, and ArgumentOutOfRangeException
  h2  NullReferenceException, IndexOutOfRangeException, and AccessViolationException
  h2  StackOverflowException
  h2  OutOfMemoryException
  h2  ComException, SEHException, and ExecutionEngineException
  h2  See also
```

### [Virtual Members](virtual-members.md)

```
h1  Virtual Members
  h2  See also
```

## 4. 正文外链登记（未收录，含判定理由）

以下为正文中指向本站其他分区的链接，按分区汇总。它们不在本次收录范围内：

| 目标分区 | 正文引用次数 |
| --- | --- |
| /en-us/dotnet/api | 163 |
| /en-us/dotnet/standard | 8 |
| /en-us/dotnet/csharp | 1 |
| /en-us/visualstudio/ide | 1 |

判定理由：`dotnet/api/...` 是类型与成员的签名参考页，本身不是设计指南；`/en-us/dotnet/standard` 下的垃圾回收等、`/en-us/dotnet/csharp` 与 `/en-us/visualstudio/ide` 的页面属其他文档集；informit.com 为原书购买页。它们不属于本指南章节，故不收录，正文中保留为绝对地址，可在线跳转。

## 5. 许可

本站点内容采用 CC BY 4.0（上游文档仓库 dotnet/docs） 许可。转载与再分发请遵循该许可的署名与相同方式共享要求。
