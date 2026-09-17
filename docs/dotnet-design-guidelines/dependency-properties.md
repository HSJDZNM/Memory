---
title: "Dependency Properties"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/dependency-properties/"
role: "指南文档 · Dependency properties"
why: "上游目录路径：Framework design guidelines > Common design patterns > Dependency properties（同级第 1 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Dependency Properties

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

A dependency property (DP) is a regular property that stores its value in a property store instead of storing it in a type variable (field), for example.

An attached dependency property is a kind of dependency property modeled as static Get and Set methods representing "properties" describing relationships between objects and their containers (e.g., the position of a `Button` object on a `Panel` container).

✔️ DO provide the dependency properties, if you need the properties to support WPF features such as styling, triggers, data binding, animations, dynamic resources, and inheritance.

## Dependency Property Design

✔️ DO inherit from [DependencyObject](https://learn.microsoft.com/en-us/dotnet/api/system.windows.dependencyobject), or one of its subtypes, when implementing dependency properties. The type provides a very efficient implementation of a property store and automatically supports WPF data binding.

✔️ DO provide a regular CLR property and public static read-only field storing an instance of [System.Windows.DependencyProperty](https://learn.microsoft.com/en-us/dotnet/api/system.windows.dependencyproperty) for each dependency property.

✔️ DO implement dependency properties by calling instance methods [DependencyObject.GetValue](https://learn.microsoft.com/en-us/dotnet/api/system.windows.dependencyobject.getvalue) and [DependencyObject.SetValue](https://learn.microsoft.com/en-us/dotnet/api/system.windows.dependencyobject.setvalue).

✔️ DO name the dependency property static field by suffixing the name of the property with "Property."

❌ DO NOT set default values of dependency properties explicitly in code; set them in metadata instead.

If you set a property default explicitly, you might prevent that property from being set by some implicit means, such as a styling.

❌ DO NOT put code in the property accessors other than the standard code to access the static field.

That code won’t execute if the property is set by implicit means, such as a styling, because styling uses the static field directly.

❌ DO NOT use dependency properties to store secure data. Even private dependency properties can be accessed publicly.

## Attached Dependency Property Design

Dependency properties described in the preceding section represent intrinsic properties of the declaring type; for example, the `Text` property is a property of `TextButton`, which declares it. A special kind of dependency property is the attached dependency property.

A classic example of an attached property is the [Grid.Column](https://learn.microsoft.com/en-us/dotnet/api/system.windows.controls.grid.column#system-windows-controls-grid-column) property. The property represents Button’s (not Grid’s) column position, but it is only relevant if the Button is contained in a Grid, and so it's "attached" to Buttons by Grids.

```
<Grid>
    <Grid.ColumnDefinitions>
        <ColumnDefinition />
        <ColumnDefinition />
    </Grid.ColumnDefinitions>

    <Button Grid.Column="0">Click</Button>
    <Button Grid.Column="1">Clack</Button>
</Grid>

```

The definition of an attached property looks mostly like that of a regular dependency property, except that the accessors are represented by static Get and Set methods:

```
public class Grid {

    public static int GetColumn(DependencyObject obj) {
        return (int)obj.GetValue(ColumnProperty);
    }

    public static void SetColumn(DependencyObject obj, int value) {
        obj.SetValue(ColumnProperty,value);
    }

    public static readonly DependencyProperty ColumnProperty =
        DependencyProperty.RegisterAttached(
            "Column",
            typeof(int),
            typeof(Grid)
    );
}

```

## Dependency Property Validation

Properties often implement what is called validation. Validation logic executes when an attempt is made to change the value of a property.

Unfortunately dependency property accessors cannot contain arbitrary validation code. Instead, dependency property validation logic needs to be specified during property registration.

❌ DO NOT put dependency property validation logic in the property’s accessors. Instead, pass a validation callback to `DependencyProperty.Register` method.

## Dependency Property Change Notifications

❌ DO NOT implement change notification logic in dependency property accessors. Dependency properties have a built-in change notifications feature that must be used by supplying a change notification callback to the [PropertyMetadata](https://learn.microsoft.com/en-us/dotnet/api/system.windows.propertymetadata).

## Dependency Property Value Coercion

Property coercion takes place when the value given to a property setter is modified by the setter before the property store is actually modified.

❌ DO NOT implement coercion logic in dependency property accessors.

Dependency properties have a built-in coercion feature, and it can be used by supplying a coercion callback to the `PropertyMetadata`.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Framework Design Guidelines](index.md)
  * [Common Design Patterns](common-design-patterns.md)

_源站标注：Last updated on 2023-10-03_
