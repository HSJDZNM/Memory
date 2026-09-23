---
title: "Using Standard Exception Types"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/using-standard-exception-types/"
role: "指南文档 · Use standard exception types"
why: "上游目录路径：Framework design guidelines > Exception design guidelines > Use standard exception types（同级第 2 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Using Standard Exception Types

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

This section describes the standard exceptions provided by the Framework and the details of their usage. The list is by no means exhaustive. Please refer to the .NET Framework reference documentation for usage of other Framework exception types.

## Exception and SystemException

❌ DO NOT throw [System.Exception](https://learn.microsoft.com/en-us/dotnet/api/system.exception) or [System.SystemException](https://learn.microsoft.com/en-us/dotnet/api/system.systemexception).

❌ DO NOT catch `System.Exception` or `System.SystemException` in framework code, unless you intend to rethrow.

❌ AVOID catching `System.Exception` or `System.SystemException`, except in top-level exception handlers.

## ApplicationException

❌ DO NOT throw or derive from [ApplicationException](https://learn.microsoft.com/en-us/dotnet/api/system.applicationexception).

## InvalidOperationException

✔️ DO throw an [InvalidOperationException](https://learn.microsoft.com/en-us/dotnet/api/system.invalidoperationexception) if the object is in an inappropriate state.

## ArgumentException, ArgumentNullException, and ArgumentOutOfRangeException

✔️ DO throw [ArgumentException](https://learn.microsoft.com/en-us/dotnet/api/system.argumentexception) or one of its subtypes if bad arguments are passed to a member. Prefer the most derived exception type, if applicable.

✔️ DO set the `ParamName` property when throwing one of the subclasses of `ArgumentException`.

This property represents the name of the parameter that caused the exception to be thrown. Note that the property can be set using one of the constructor overloads.

✔️ DO use `value` for the name of the implicit value parameter of property setters.

## NullReferenceException, IndexOutOfRangeException, and AccessViolationException

❌ DO NOT allow publicly callable APIs to explicitly or implicitly throw [NullReferenceException](https://learn.microsoft.com/en-us/dotnet/api/system.nullreferenceexception), [AccessViolationException](https://learn.microsoft.com/en-us/dotnet/api/system.accessviolationexception), or [IndexOutOfRangeException](https://learn.microsoft.com/en-us/dotnet/api/system.indexoutofrangeexception). These exceptions are reserved and thrown by the execution engine and in most cases indicate a bug.

Do argument checking to avoid throwing these exceptions. Throwing these exceptions exposes implementation details of your method that might change over time.

## StackOverflowException

❌ DO NOT explicitly throw [StackOverflowException](https://learn.microsoft.com/en-us/dotnet/api/system.stackoverflowexception). The exception should be explicitly thrown only by the CLR.

❌ DO NOT catch `StackOverflowException`.

It is almost impossible to write managed code that remains consistent in the presence of arbitrary stack overflows. The unmanaged parts of the CLR remain consistent by using probes to move stack overflows to well-defined places rather than by backing out from arbitrary stack overflows.

## OutOfMemoryException

❌ DO NOT explicitly throw [OutOfMemoryException](https://learn.microsoft.com/en-us/dotnet/api/system.outofmemoryexception). This exception is to be thrown only by the CLR infrastructure.

## ComException, SEHException, and ExecutionEngineException

❌ DO NOT explicitly throw [COMException](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.comexception), [ExecutionEngineException](https://learn.microsoft.com/en-us/dotnet/api/system.executionengineexception), and [SEHException](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.sehexception). These exceptions are to be thrown only by the CLR infrastructure.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Design Guidelines for Exceptions](exceptions.md)

_源站标注：Last updated on 2023-10-03_
