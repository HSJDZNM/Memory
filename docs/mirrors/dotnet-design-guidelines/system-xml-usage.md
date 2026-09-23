---
title: "System.Xml Usage"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/system-xml-usage/"
role: "指南文档 · System.Xml usage"
why: "上游目录路径：Framework design guidelines > Usage guidelines > System.Xml usage（同级第 5 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# System.Xml Usage

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

This section talks about usage of several types residing in [System.Xml](https://learn.microsoft.com/en-us/dotnet/api/system.xml) namespaces that can be used to represent XML data.

❌ DO NOT use [XmlNode](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xmlnode) or [XmlDocument](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xmldocument) to represent XML data. Favor using instances of [IXPathNavigable](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xpath.ixpathnavigable), [XmlReader](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xmlreader), [XmlWriter](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xmlwriter), or subtypes of [XNode](https://learn.microsoft.com/en-us/dotnet/api/system.xml.linq.xnode) instead. `XmlNode` and `XmlDocument` are not designed for exposing in public APIs.

✔️ DO use `XmlReader`, `IXPathNavigable`, or subtypes of `XNode` as input or output of members that accept or return XML.

Use these abstractions instead of `XmlDocument`, `XmlNode`, or [XPathDocument](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xpath.xpathdocument), because this decouples the methods from specific implementations of an in-memory XML document and allows them to work with virtual XML data sources that expose `XNode`, `XmlReader`, or [XPathNavigator](https://learn.microsoft.com/en-us/dotnet/api/system.xml.xpath.xpathnavigator).

❌ DO NOT subclass `XmlDocument` if you want to create a type representing an XML view of an underlying object model or data source.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Usage Guidelines](usage-guidelines.md)

_源站标注：Last updated on 2023-10-03_
