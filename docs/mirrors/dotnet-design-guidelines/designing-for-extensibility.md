---
title: "Designing for Extensibility"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/designing-for-extensibility/"
role: "章节索引 · Design for extensibility"
why: "该章节目录节点本身也是页面；上游目录路径：Framework design guidelines > Design for extensibility"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Designing for Extensibility

One important aspect of designing a framework is making sure the extensibility of the framework has been carefully considered. This requires that you understand the costs and benefits associated with various extensibility mechanisms. This chapter helps you decide which of the extensibility mechanisms—subclassing, events, virtual members, callbacks, and so on—can best meet the requirements of your framework.

There are many ways to allow extensibility in frameworks. They range from less powerful but less costly to very powerful but expensive. For any given extensibility requirement, you should choose the least costly extensibility mechanism that meets the requirements. Keep in mind that it’s usually possible to add more extensibility later, but you can never take it away without introducing breaking changes.

## In This Section

[Unsealed Classes](unsealed-classes.md)
[Protected Members](protected-members.md)
[Events and Callbacks](events-and-callbacks.md)
[Virtual Members](virtual-members.md)
[Abstractions (Abstract Types and Interfaces)](abstractions-abstract-types-and-interfaces.md)
[Base Classes for Implementing Abstractions](base-classes-for-implementing-abstractions.md)
[Sealing](sealing.md)
_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2022-04-01_
