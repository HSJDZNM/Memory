---
title: "Exceptions and Performance"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/exceptions-and-performance/"
role: "指南文档 · Exceptions and performance"
why: "上游目录路径：Framework design guidelines > Exception design guidelines > Exceptions and performance（同级第 3 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Exceptions and Performance

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

One common concern related to exceptions is that if exceptions are used for code that routinely fails, the performance of the implementation will be unacceptable. This is a valid concern. When a member throws an exception, its performance can be orders of magnitude slower. However, it is possible to achieve good performance while strictly adhering to the exception guidelines that disallow using error codes. Two patterns described in this section suggest ways to do this.

❌ DO NOT use error codes because of concerns that exceptions might affect performance negatively.

To improve performance, it is possible to use either the Tester-Doer Pattern or the Try-Parse Pattern, described in the next two sections.

## Tester-Doer Pattern

Sometimes performance of an exception-throwing member can be improved by breaking the member into two. Let’s look at the [Add](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.icollection-1.add) method of the [ICollection<T>](https://learn.microsoft.com/en-us/dotnet/api/system.collections.generic.icollection-1) interface.

```
ICollection<int> numbers = ...
numbers.Add(1);

```

The method `Add` throws if the collection is read-only. This can be a performance problem in scenarios where the method call is expected to fail often. One of the ways to mitigate the problem is to test whether the collection is writable before trying to add a value.

```
ICollection<int> numbers = ...
...
if (!numbers.IsReadOnly)
{
    numbers.Add(1);
}

```

The member used to test a condition, which in our example is the property `IsReadOnly`, is referred to as the tester. The member used to perform a potentially throwing operation, the `Add` method in our example, is referred to as the doer.

✔️ CONSIDER the Tester-Doer Pattern for members that might throw exceptions in common scenarios to avoid performance problems related to exceptions.

## Try-Parse Pattern

For extremely performance-sensitive APIs, an even faster pattern than the Tester-Doer Pattern described in the previous section should be used. The pattern calls for adjusting the member name to make a well-defined test case a part of the member semantics. For example, [DateTime](https://learn.microsoft.com/en-us/dotnet/api/system.datetime) defines a [Parse](https://learn.microsoft.com/en-us/dotnet/api/system.datetime.parse) method that throws an exception if parsing of a string fails. It also defines a corresponding [TryParse](https://learn.microsoft.com/en-us/dotnet/api/system.datetime.tryparse) method that attempts to parse, but returns false if parsing is unsuccessful and returns the result of a successful parsing using an `out` parameter.

```
public struct DateTime
{
    public static DateTime Parse(string dateTime)
    {
        ...
    }
    public static bool TryParse(string dateTime, out DateTime result)
    {
        ...
    }
}

```

When using this pattern, it is important to define the try functionality in strict terms. If the member fails for any reason other than the well-defined try, the member must still throw a corresponding exception.

✔️ CONSIDER the Try-Parse Pattern for members that might throw exceptions in common scenarios to avoid performance problems related to exceptions.

✔️ DO use the prefix "Try" and Boolean return type for methods implementing this pattern.

✔️ DO provide an exception-throwing member for each member using the Try-Parse Pattern.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Design Guidelines for Exceptions](exceptions.md)

_源站标注：Last updated on 2023-10-03_
