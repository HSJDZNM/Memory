---
title: "Names of Namespaces"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/names-of-namespaces/"
role: "指南文档 · Names of namespaces"
why: "上游目录路径：Framework design guidelines > Naming guidelines > Names of namespaces（同级第 4 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Names of Namespaces

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

As with other naming guidelines, the goal when naming namespaces is creating sufficient clarity for the programmer using the framework to immediately know what the content of the namespace is likely to be. The following template specifies the general rule for naming namespaces:

`<Company>.(<Product>|<Technology>)[.<Feature>][.<Subnamespace>]`

The following are examples:

`Fabrikam.Math` `Litware.Security`

✔️ DO prefix namespace names with a company name to prevent namespaces from different companies from having the same name.

✔️ DO use a stable, version-independent product name at the second level of a namespace name.

❌ DO NOT use organizational hierarchies as the basis for names in namespace hierarchies, because group names within corporations tend to be short-lived. Organize the hierarchy of namespaces around groups of related technologies.

✔️ DO use PascalCasing, and separate namespace components with periods (e.g., `Microsoft.Office.PowerPoint`). If your brand employs nontraditional casing, you should follow the casing defined by your brand, even if it deviates from normal namespace casing.

✔️ CONSIDER using plural namespace names where appropriate.

For example, use `System.Collections` instead of `System.Collection`. Brand names and acronyms are exceptions to this rule, however. For example, use `System.IO` instead of `System.IOs`.

❌ DO NOT use the same name for a namespace and a type in that namespace.

For example, do not use `Debug` as a namespace name and then also provide a class named `Debug` in the same namespace. Several compilers require such types to be fully qualified.

### Namespaces and Type Name Conflicts

❌ DO NOT introduce generic type names such as `Element`, `Node`, `Log`, and `Message`.

There is a very high probability that doing so will lead to type name conflicts in common scenarios. You should qualify the generic type names (`FormElement`, `XmlNode`, `EventLog`, `SoapMessage`).

There are specific guidelines for avoiding type name conflicts for different categories of namespaces.

  * **Application model namespaces**

Namespaces belonging to a single application model are very often used together, but they are almost never used with namespaces of other application models. For example, the [System.Windows.Forms](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms) namespace is very rarely used together with the [System.Web.UI](https://learn.microsoft.com/en-us/dotnet/api/system.web.ui) namespace. The following is a list of well-known application model namespace groups:

`System.Windows*` `System.Web.UI*`

❌ DO NOT give the same name to types in namespaces within a single application model.

For example, do not add a type named `Page` to the [System.Web.UI.Adapters](https://learn.microsoft.com/en-us/dotnet/api/system.web.ui.adapters) namespace, because the [System.Web.UI](https://learn.microsoft.com/en-us/dotnet/api/system.web.ui) namespace already contains a type named `Page`.

  * **Infrastructure namespaces**

This group contains namespaces that are rarely imported during development of common applications. For example, `.Design` namespaces are mainly used when developing programming tools. Avoiding conflicts with types in these namespaces is not critical.

  * **Core namespaces**

Core namespaces include all `System` namespaces, excluding namespaces of the application models and the Infrastructure namespaces. Core namespaces include, among others, `System`, `System.IO`, `System.Xml`, and `System.Net`.

❌ DO NOT give types names that would conflict with any type in the Core namespaces.

For example, never use `Stream` as a type name. It would conflict with [System.IO.Stream](https://learn.microsoft.com/en-us/dotnet/api/system.io.stream), a very commonly used type.

  * **Technology namespace groups**

This category includes all namespaces with the same first two namespace nodes `(<Company>.<Technology>*`), such as `Microsoft.Build.Utilities` and `Microsoft.Build.Tasks`. It is important that types belonging to a single technology do not conflict with each other.

❌ DO NOT assign type names that would conflict with other types within a single technology.

❌ DO NOT introduce type name conflicts between types in technology namespaces and an application model namespace (unless the technology is not intended to be used with the application model).

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Naming Guidelines](naming-guidelines.md)

_源站标注：Last updated on 2023-10-03_
