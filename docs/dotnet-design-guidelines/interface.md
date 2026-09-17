---
title: "Interface Design"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/interface/"
role: "指南文档 · Interface design"
why: "上游目录路径：Framework design guidelines > Type design guidelines > Interface design（同级第 4 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Interface Design

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Although most APIs are best modeled using classes and structs, there are cases in which interfaces are more appropriate or are the only option.

The CLR does not support multiple inheritance (i.e., CLR classes cannot inherit from more than one base class), but it does allow types to implement one or more interfaces in addition to inheriting from a base class. Therefore, interfaces are often used to achieve the effect of multiple inheritance. For example, [IDisposable](https://learn.microsoft.com/en-us/dotnet/api/system.idisposable) is an interface that allows types to support disposability independent of any other inheritance hierarchy in which they want to participate.

The other situation in which defining an interface is appropriate is in creating a common interface that can be supported by several types, including some value types. Value types cannot inherit from types other than [ValueType](https://learn.microsoft.com/en-us/dotnet/api/system.valuetype), but they can implement interfaces, so using an interface is the only option in order to provide a common base type.

✔️ DO define an interface if you need some common API to be supported by a set of types that includes value types.

✔️ CONSIDER defining an interface if you need to support its functionality on types that already inherit from some other type.

❌ AVOID using marker interfaces (interfaces with no members).

If you need to mark a class as having a specific characteristic (marker), in general, use a custom attribute rather than an interface.

✔️ DO provide at least one type that is an implementation of an interface.

Doing this helps to validate the design of the interface. For example, [List<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.list-1) is an implementation of the [IList<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.ilist-1) interface.

✔️ DO provide at least one API that consumes each interface you define (a method taking the interface as a parameter or a property typed as the interface).

Doing this helps to validate the interface design. For example, [List<T>.Sort](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.list-1.sort) consumes the [System.Collections.Generic.IComparer<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.icomparer-1) interface.

❌ DO NOT add members to an interface that has previously shipped.

Doing so would break implementations of the interface. You should create a new interface in order to avoid versioning problems.

Except for the situations described in these guidelines, you should, in general, choose classes rather than interfaces in designing managed code reusable libraries.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Type Design Guidelines](type.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
