---
title: "Property Design"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/property/"
role: "指南文档 · Property design"
why: "上游目录路径：Framework design guidelines > Member design guidelines > Property design（同级第 2 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Property Design

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Although properties are technically very similar to methods, they are quite different in terms of their usage scenarios. They should be seen as smart fields. They have the calling syntax of fields, and the flexibility of methods.

✔️ DO create get-only properties if the caller should not be able to change the value of the property.

Keep in mind that if the type of the property is a mutable reference type, the property value can be changed even if the property is get-only.

❌ DO NOT provide set-only properties or properties with the setter having broader accessibility than the getter.

For example, do not use properties with a public setter and a protected getter.

If the property getter cannot be provided, implement the functionality as a method instead. Consider starting the method name with `Set` and follow with what you would have named the property. For example, [AppDomain](https://learn.microsoft.com/en-us/dotnet/api/system.appdomain) has a method called `SetCachePath` instead of having a set-only property called `CachePath`.

✔️ DO provide sensible default values for all properties, ensuring that the defaults do not result in a security hole or terribly inefficient code.

✔️ DO allow properties to be set in any order even if this results in a temporary invalid state of the object.

It is common for two or more properties to be interrelated to a point where some values of one property might be invalid given the values of other properties on the same object. In such cases, exceptions resulting from the invalid state should be postponed until the interrelated properties are actually used together by the object.

✔️ DO preserve the previous value if a property setter throws an exception.

❌ AVOID throwing exceptions from property getters.

Property getters should be simple operations and should not have any preconditions. If a getter can throw an exception, it should probably be redesigned to be a method. Notice that this rule does not apply to indexers, where we do expect exceptions as a result of validating the arguments.

### Indexed Property Design

An indexed property is a special property that can have parameters and can be called with special syntax similar to array indexing.

Indexed properties are commonly referred to as indexers. Indexers should be used only in APIs that provide access to items in a logical collection. For example, a string is a collection of characters, and the indexer on [System.String](https://learn.microsoft.com/en-us/dotnet/api/system.string) was added to access its characters.

✔️ CONSIDER using indexers to provide access to data stored in an internal array.

✔️ CONSIDER providing indexers on types representing collections of items.

❌ AVOID using indexed properties with more than one parameter.

If the design requires multiple parameters, reconsider whether the property really represents an accessor to a logical collection. If it does not, use methods instead. Consider starting the method name with `Get` or `Set`.

❌ AVOID indexers with parameter types other than [System.Int32](https://learn.microsoft.com/en-us/dotnet/api/system.int32), [System.Int64](https://learn.microsoft.com/en-us/dotnet/api/system.int64), [System.String](https://learn.microsoft.com/en-us/dotnet/api/system.string), [System.Object](https://learn.microsoft.com/en-us/dotnet/api/system.object), or an enum.

If the design requires other types of parameters, strongly reevaluate whether the API really represents an accessor to a logical collection. If it does not, use a method. Consider starting the method name with `Get` or `Set`.

✔️ DO use the name `Item` for indexed properties unless there is an obviously better name (e.g., see the [Chars[]](https://learn.microsoft.com/en-us/dotnet/api/system.string.chars) property on `System.String`).

In C#, indexers are by default named Item. The [IndexerNameAttribute](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.compilerservices.indexernameattribute) can be used to customize this name.

❌ DO NOT provide both an indexer and methods that are semantically equivalent.

❌ DO NOT provide more than one family of overloaded indexers in one type.

This is enforced by the C# compiler.

❌ DO NOT use nondefault indexed properties.

This is enforced by the C# compiler.

### Property Change Notification Events

Sometimes it is useful to provide an event notifying the user of changes in a property value. For example, `System.Windows.Forms.Control` raises a `TextChanged` event after the value of its `Text` property has changed.

✔️ CONSIDER raising change notification events when property values in high-level APIs (usually designer components) are modified.

If there is a good scenario for a user to know when a property of an object is changing, the object should raise a change notification event for the property.

However, it is unlikely to be worth the overhead to raise such events for low-level APIs such as base types or collections. For example, [List<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.list-1) would not raise such events when a new item is added to the list and the `Count` property changes.

✔️ CONSIDER raising change notification events when the value of a property changes via external forces.

If a property value changes via some external force (in a way other than by calling methods on the object), raise events indicate to the developer that the value is changing and has changed. A good example is the `Text` property of a text box control. When the user types text in a `TextBox`, the property value automatically changes.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Member Design Guidelines](member.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
