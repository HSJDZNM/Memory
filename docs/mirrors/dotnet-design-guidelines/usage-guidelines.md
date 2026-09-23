---
title: "Usage guidelines"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/usage-guidelines/"
role: "章节索引 · Usage guidelines"
why: "该章节目录节点本身也是页面；上游目录路径：Framework design guidelines > Usage guidelines"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Usage guidelines

This section contains guidelines for using common types in publicly accessible APIs. It deals with direct usage of built-in Framework types (e.g., serialization attributes) and overloading common operators.

The [System.IDisposable](https://learn.microsoft.com/en-us/dotnet/api/system.idisposable) interface is not covered in this section, but is discussed in the [Dispose Pattern](dispose-pattern.md) section.

Note

For guidelines and additional information about other common, built-in .NET Framework types, see the reference topics for the following: [System.DateTime](https://learn.microsoft.com/en-us/dotnet/api/system.datetime), [System.DateTimeOffset](https://learn.microsoft.com/en-us/dotnet/api/system.datetimeoffset), [System.ICloneable](https://learn.microsoft.com/en-us/dotnet/api/system.icloneable), [System.IComparable<T>](https://learn.microsoft.com/en-us/dotnet/api/system.icomparable-1), [System.IEquatable<T>](https://learn.microsoft.com/en-us/dotnet/api/system.iequatable-1), [System.Nullable<T>](https://learn.microsoft.com/en-us/dotnet/api/system.nullable-1), [System.Object](https://learn.microsoft.com/en-us/dotnet/api/system.object), [System.Uri](https://learn.microsoft.com/en-us/dotnet/api/system.uri).

## In this section

[Arrays](arrays.md)
[Attributes](attributes.md)
[Collections](guidelines-for-collections.md)
[Serialization](serialization.md)
[System.Xml Usage](system-xml-usage.md)
[Equality Operators](equality-operators.md)

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2024-03-27_
