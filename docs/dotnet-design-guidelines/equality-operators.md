---
title: "Equality Operators"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/equality-operators/"
role: "指南文档 · Equality operators"
why: "上游目录路径：Framework design guidelines > Usage guidelines > Equality operators（同级第 6 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Equality Operators

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

This section discusses overloading equality operators and refers to `operator==` and `operator!=` as equality operators.

❌ DO NOT overload one of the equality operators and not the other.

✔️ DO ensure that [Object.Equals](https://learn.microsoft.com/en-us/dotnet/api/system.object.equals) and the equality operators have exactly the same semantics and similar performance characteristics.

This often means that `Object.Equals` needs to be overridden when the equality operators are overloaded.

❌ AVOID throwing exceptions from equality operators.

For example, return false if one of the arguments is null instead of throwing `NullReferenceException`.

## Equality Operators on Value Types

✔️ DO overload the equality operators on value types, if equality is meaningful.

In most programming languages, there is no default implementation of `operator==` for value types.

## Equality Operators on Reference Types

❌ AVOID overloading equality operators on mutable reference types.

Many languages have built-in equality operators for reference types. The built-in operators usually implement the reference equality, and many developers are surprised when the default behavior is changed to the value equality.

This problem is mitigated for immutable reference types because immutability makes it much harder to notice the difference between reference equality and value equality.

❌ AVOID overloading equality operators on reference types if the implementation would be significantly slower than that of reference equality.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Usage Guidelines](usage-guidelines.md)

_源站标注：Last updated on 2023-10-03_
