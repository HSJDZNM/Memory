---
title: "Naming Resources"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/naming-resources/"
role: "指南文档 · Naming resources"
why: "上游目录路径：Framework design guidelines > Naming guidelines > Naming resources（同级第 8 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Naming Resources

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Because localizable resources can be referenced via certain objects as if they were properties, the naming guidelines for resources are similar to property guidelines.

✔️ DO use PascalCasing in resource keys.

✔️ DO provide descriptive rather than short identifiers.

❌ DO NOT use language-specific keywords of the main CLR languages.

✔️ DO use only alphanumeric characters and underscores in naming resources.

✔️ DO use the following naming convention for exception message resources.

The resource identifier should be the exception type name plus a short identifier of the exception:

`ArgumentExceptionIllegalCharacters` `ArgumentExceptionInvalidName` `ArgumentExceptionFileNameIsMalformed`

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Naming Guidelines](naming-guidelines.md)

_源站标注：Last updated on 2023-10-03_
