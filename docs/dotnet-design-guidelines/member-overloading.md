---
title: "Member Overloading"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/member-overloading/"
role: "指南文档 · Member overloading"
why: "上游目录路径：Framework design guidelines > Member design guidelines > Member overloading（同级第 1 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Member Overloading

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Member overloading means creating two or more members on the same type that differ only in the number or type of parameters but have the same name. For example, in the following, the `WriteLine` method is overloaded:

```
public static class Console {
    public void WriteLine();
    public void WriteLine(string value);
    public void WriteLine(bool value);
    ...
}

```

Because only methods, constructors, and indexed properties can have parameters, only those members can be overloaded.

Overloading is one of the most important techniques for improving usability, productivity, and readability of reusable libraries. Overloading on the number of parameters makes it possible to provide simpler versions of constructors and methods. Overloading on the parameter type makes it possible to use the same member name for members performing identical operations on a selected set of different types.

✔️ DO try to use descriptive parameter names to indicate the default used by shorter overloads.

❌ AVOID arbitrarily varying parameter names in overloads. If a parameter in one overload represents the same input as a parameter in another overload, the parameters should have the same name.

❌ AVOID being inconsistent in the ordering of parameters in overloaded members. Parameters with the same name should appear in the same position in all overloads.

✔️ DO make only the longest overload virtual (if extensibility is required). Shorter overloads should simply call through to a longer overload.

❌ DO NOT use `ref` or `out` modifiers to overload members.

Some languages cannot resolve calls to overloads like this. In addition, such overloads usually have completely different semantics and probably should not be overloads but two separate methods instead.

❌ DO NOT have overloads with parameters at the same position and similar types yet with different semantics.

✔️ DO allow `null` to be passed for optional arguments.

✔️ DO use member overloading rather than defining members with default arguments.

Default arguments are not CLS compliant.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Member Design Guidelines](member.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2023-10-03_
