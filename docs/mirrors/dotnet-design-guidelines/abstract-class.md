---
title: "Abstract Class Design"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/abstract-class/"
role: "指南文档 · Abstract class design"
why: "上游目录路径：Framework design guidelines > Type design guidelines > Abstract class design（同级第 2 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Abstract Class Design

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

❌ DO NOT define public or protected internal constructors in abstract types.

Constructors should be public only if users will need to create instances of the type. Because you cannot create instances of an abstract type, an abstract type with a public constructor is incorrectly designed and misleading to the users.

✔️ DO define a protected or an internal constructor in abstract classes.

A protected constructor is more common and simply allows the base class to do its own initialization when subtypes are created.

An internal constructor can be used to limit concrete implementations of the abstract class to the assembly defining the class.

✔️ DO provide at least one concrete type that inherits from each abstract class that you ship.

Doing this helps to validate the design of the abstract class. For example, [System.IO.FileStream](https://learn.microsoft.com/en-us/dotnet/api/system.io.filestream) is an implementation of the [System.IO.Stream](https://learn.microsoft.com/en-us/dotnet/api/system.io.stream) abstract class.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Type Design Guidelines](type.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
