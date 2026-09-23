---
title: "Static Class Design"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/static-class/"
role: "指南文档 · Static class design"
why: "上游目录路径：Framework design guidelines > Type design guidelines > Static class design（同级第 3 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Static Class Design

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

A static class is defined as a class that contains only static members (of course besides the instance members inherited from [System.Object](https://learn.microsoft.com/en-us/dotnet/api/system.object) and possibly a private constructor). Some languages provide built-in support for static classes. In C# 2.0 and later, when a class is declared to be static, it is sealed, abstract, and no instance members can be overridden or declared.

Static classes are a compromise between pure object-oriented design and simplicity. They are commonly used to provide shortcuts to other operations (such as [System.IO.File](https://learn.microsoft.com/en-us/dotnet/api/system.io.file)), holders of extension methods, or functionality for which a full object-oriented wrapper is unwarranted (such as [System.Environment](https://learn.microsoft.com/en-us/dotnet/api/system.environment)).

✔️ DO use static classes sparingly.

Static classes should be used only as supporting classes for the object-oriented core of the framework.

❌ DO NOT treat static classes as a miscellaneous bucket.

❌ DO NOT declare or override instance members in static classes.

✔️ DO declare static classes as sealed, abstract, and add a private instance constructor if your programming language does not have built-in support for static classes.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Type Design Guidelines](type.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
