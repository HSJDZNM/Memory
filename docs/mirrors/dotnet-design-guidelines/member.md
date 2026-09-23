---
title: "Member Design Guidelines"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/member/"
role: "章节索引 · Member design guidelines"
why: "该章节目录节点本身也是页面；上游目录路径：Framework design guidelines > Member design guidelines"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Member Design Guidelines

Methods, properties, events, constructors, and fields are collectively referred to as members. Members are ultimately the means by which framework functionality is exposed to the end users of a framework.

Members can be virtual or nonvirtual, concrete or abstract, static or instance, and can have several different scopes of accessibility. All this variety provides incredible expressiveness but at the same time requires care on the part of the framework designer.

This chapter offers basic guidelines that should be followed when designing members of any type.

## In This Section

[Member Overloading](member-overloading.md)
[Property Design](property.md)
[Constructor Design](constructor.md)
[Event Design](event.md)
[Field Design](field.md)
[Extension Methods](extension-methods.md)
[Operator Overloads](operator-overloads.md)
[Parameter Design](parameter-design.md)
_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2022-04-01_
