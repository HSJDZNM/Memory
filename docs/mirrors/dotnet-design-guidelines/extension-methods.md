---
title: "Extension Methods"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/extension-methods/"
role: "指南文档 · Extension methods"
why: "上游目录路径：Framework design guidelines > Member design guidelines > Extension methods（同级第 6 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Extension Methods

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Extension methods are a language feature that allows static methods to be called using instance method call syntax. These methods must take at least one parameter, which represents the instance the method is to operate on.

The class that defines such extension methods is referred to as the "sponsor" class, and it must be declared as static. To use extension methods, one must import the namespace defining the sponsor class.

❌ AVOID frivolously defining extension methods, especially on types you don't own.

If you do own source code of a type, consider using regular instance methods instead. If you don't own, and you want to add a method, be very careful. Liberal use of extension methods has the potential of cluttering APIs of types that were not designed to have these methods.

✔️ CONSIDER using extension methods in any of the following scenarios:

  * To provide helper functionality relevant to every implementation of an interface, if said functionality can be written in terms of the core interface. This is because concrete implementations cannot otherwise be assigned to interfaces. For example, the `LINQ to Objects` operators are implemented as extension methods for all [IEnumerable<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.ienumerable-1) types. Thus, any `IEnumerable<>` implementation is automatically LINQ-enabled.

  * When an instance method would introduce a dependency on some type, but such a dependency would break dependency management rules. For example, a dependency from [String](https://learn.microsoft.com/en-us/dotnet/api/system.string) to [System.Uri](https://learn.microsoft.com/en-us/dotnet/api/system.uri) is probably not desirable, and so `String.ToUri()` instance method returning `System.Uri` would be the wrong design from a dependency management perspective. A static extension method `Uri.ToUri(this string str)` returning `System.Uri` would be a much better design.

❌ AVOID defining extension methods on [System.Object](https://learn.microsoft.com/en-us/dotnet/api/system.object).

VB users will not be able to call such methods on object references using the extension method syntax. VB does not support calling such methods because, in VB, declaring a reference as Object forces all method invocations on it to be late bound (actual member called is determined at run time), while bindings to extension methods are determined at compile-time (early bound).

Note that the guideline applies to other languages where the same binding behavior is present, or where extension methods are not supported.

❌ DO NOT put extension methods in the same namespace as the extended type unless it is for adding methods to interfaces or for dependency management.

❌ AVOID defining two or more extension methods with the same signature, even if they reside in different namespaces.

✔️ CONSIDER defining extension methods in the same namespace as the extended type if the type is an interface and if the extension methods are meant to be used in most or all cases.

❌ DO NOT define extension methods implementing a feature in namespaces normally associated with other features. Instead, define them in the namespace associated with the feature they belong to.

❌ AVOID generic naming of namespaces dedicated to extension methods (e.g., "Extensions"). Use a descriptive name (e.g., "Routing") instead.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Member Design Guidelines](member.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
