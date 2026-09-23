---
title: "Base Classes for Implementing Abstractions"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/base-classes-for-implementing-abstractions/"
role: "指南文档 · Base classes for implementing abstractions"
why: "上游目录路径：Framework design guidelines > Design for extensibility > Base classes for implementing abstractions（同级第 6 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Base Classes for Implementing Abstractions

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Strictly speaking, a class becomes a base class when another class is derived from it. For the purpose of this section, however, a base class is a class designed mainly to provide a common abstraction or for other classes to reuse some default implementation though inheritance. Base classes usually sit in the middle of inheritance hierarchies, between an abstraction at the root of a hierarchy and several custom implementations at the bottom.

They serve as implementation helpers for implementing abstractions. For example, one of the Framework’s abstractions for ordered collections of items is the [IList<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.ilist-1) interface. Implementing [IList<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.ilist-1) is not trivial, and therefore the Framework provides several base classes, such as [Collection<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.objectmodel.collection-1) and [KeyedCollection<TKey,TItem>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.objectmodel.keyedcollection-2), which serve as helpers for implementing custom collections.

Base classes are usually not suited to serve as abstractions by themselves, because they tend to contain too much implementation. For example, the `Collection<T>` base class contains lots of implementation related to the fact that it implements the nongeneric `IList` interface (to integrate better with nongeneric collections) and to the fact that it is a collection of items stored in memory in one of its fields.

As previously discussed, base classes can provide invaluable help for users who need to implement abstractions, but at the same time they can be a significant liability. They add surface area and increase the depth of inheritance hierarchies and so conceptually complicate the framework. Therefore, base classes should be used only if they provide significant value to the users of the framework. They should be avoided if they provide value only to the implementers of the framework, in which case delegation to an internal implementation instead of inheritance from a base class should be strongly considered.

✔️ CONSIDER making base classes abstract even if they don’t contain any abstract members. This clearly communicates to the users that the class is designed solely to be inherited from.

✔️ CONSIDER placing base classes in a separate namespace from the mainline scenario types. By definition, base classes are intended for advanced extensibility scenarios and therefore are not interesting to the majority of users.

❌ AVOID naming base classes with a "Base" suffix if the class is intended for use in public APIs.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Designing for Extensibility](designing-for-extensibility.md)

_源站标注：Last updated on 2023-10-03_
