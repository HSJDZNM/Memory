---
title: "Field Design"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/field/"
role: "指南文档 · Field design"
why: "上游目录路径：Framework design guidelines > Member design guidelines > Field design（同级第 5 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Field Design

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

The principle of encapsulation is one of the most important notions in object-oriented design. This principle states that data stored inside an object should be accessible only to that object.

A useful way to interpret the principle is to say that a type should be designed so that changes to fields of that type (name or type changes) can be made without breaking code other than for members of the type. This interpretation immediately implies that all fields must be private.

We exclude constant and static read-only fields from this strict restriction, because such fields, almost by definition, are never required to change.

❌ DO NOT provide instance fields that are public or protected.

You should provide properties for accessing fields instead of making them public or protected.

✔️ DO use constant fields for constants that will never change.

The compiler burns the values of const fields directly into calling code. Therefore, const values can never be changed without the risk of breaking compatibility.

✔️ DO use public static `readonly` fields for predefined object instances.

If there are predefined instances of the type, declare them as public read-only static fields of the type itself.

❌ DO NOT assign instances of mutable types to `readonly` fields.

A mutable type is a type with instances that can be modified after they are instantiated. For example, arrays, most collections, and streams are mutable types, but [System.Int32](https://learn.microsoft.com/en-us/dotnet/api/system.int32), [System.Uri](https://learn.microsoft.com/en-us/dotnet/api/system.uri), and [System.String](https://learn.microsoft.com/en-us/dotnet/api/system.string) are all immutable. The read-only modifier on a reference type field prevents the instance stored in the field from being replaced, but it does not prevent the field’s instance data from being modified by calling members changing the instance.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Member Design Guidelines](member.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
