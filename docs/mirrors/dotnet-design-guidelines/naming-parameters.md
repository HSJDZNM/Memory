---
title: "Naming Parameters"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/naming-parameters/"
role: "指南文档 · Naming parameters"
why: "上游目录路径：Framework design guidelines > Naming guidelines > Naming parameters（同级第 7 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Naming Parameters

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Beyond the obvious reason of readability, it is important to follow the guidelines for parameter names because parameters are displayed in documentation and in the designer when visual design tools provide Intellisense and class browsing functionality.

✔️ DO use camelCasing in parameter names.

✔️ DO use descriptive parameter names.

✔️ CONSIDER using names based on a parameter’s meaning rather than the parameter’s type.

### Naming Operator Overload Parameters

✔️ DO use `left` and `right` for binary operator overload parameter names if there is no meaning to the parameters.

✔️ DO use `value` for unary operator overload parameter names if there is no meaning to the parameters.

✔️ CONSIDER meaningful names for operator overload parameters if doing so adds significant value.

❌ DO NOT use abbreviations or numeric indices for operator overload parameter names.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Naming Guidelines](naming-guidelines.md)

_源站标注：Last updated on 2023-10-03_
