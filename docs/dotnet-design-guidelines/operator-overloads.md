---
title: "Operator Overloads"
source_url: "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/operator-overloads/"
role: "指南文档 · Operator overloads"
why: "上游目录路径：Framework design guidelines > Member design guidelines > Operator overloads（同级第 7 篇）"
copyright: "CC BY 4.0（上游文档仓库 dotnet/docs）"
fetched_at: "2026-09-16T08:05:08Z"
---

# Operator Overloads

Note

This content is reprinted by permission of Pearson Education, Inc. from _Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition_. That edition was published in 2008, and the book has since been fully revised in the [third edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780135896464). Some of the information on this page may be out-of-date.

Operator overloads allow framework types to appear as if they were built-in language primitives.

Although allowed and useful in some situations, operator overloads should be used cautiously. There are many cases in which operator overloading has been abused, such as when framework designers started to use operators for operations that should be simple methods. The following guidelines should help you decide when and how to use operator overloading.

❌ AVOID defining operator overloads, except in types that should feel like primitive (built-in) types.

✔️ CONSIDER defining operator overloads in a type that should feel like a primitive type.

For example, [System.String](https://learn.microsoft.com/en-us/dotnet/api/system.string) has `operator==` and `operator!=` defined.

✔️ DO define operator overloads in structs that represent numbers (such as [System.Decimal](https://learn.microsoft.com/en-us/dotnet/api/system.decimal)).

❌ DO NOT be cute when defining operator overloads.

Operator overloading is useful in cases in which it is immediately obvious what the result of the operation will be. For example, it makes sense to be able to subtract one [DateTime](https://learn.microsoft.com/en-us/dotnet/api/system.datetime) from another `DateTime` and get a [TimeSpan](https://learn.microsoft.com/en-us/dotnet/api/system.timespan). However, it is not appropriate to use the logical union operator to union two database queries, or to use the shift operator to write to a stream.

❌ DO NOT provide operator overloads unless at least one of the operands is of the type defining the overload.

✔️ DO overload operators in a symmetric fashion.

For example, if you overload the `operator==`, you should also overload the `operator!=`. Similarly, if you overload the `operator<`, you should also overload the `operator>`, and so on.

✔️ CONSIDER providing methods with friendly names that correspond to each overloaded operator.

Many languages do not support operator overloading. For this reason, it is recommended that types that overload operators include a secondary method with an appropriate domain-specific name that provides equivalent functionality.

The following table contains a list of operators and the corresponding friendly method names.

| C# Operator Symbol  | Metadata Name  | Friendly Name  |
| --- | --- | --- |
| `N/A`  | `op_Implicit`  | `To<TypeName>/From<TypeName>`  |
| `N/A`  | `op_Explicit`  | `To<TypeName>/From<TypeName>`  |
| `+ (binary)`  | `op_Addition`  | `Add`  |
| `- (binary)`  | `op_Subtraction`  | `Subtract`  |
| `* (binary)`  | `op_Multiply`  | `Multiply`  |
| `/`  | `op_Division`  | `Divide`  |
| `%`  | `op_Modulus`  | `Mod or Remainder`  |
| `^`  | `op_ExclusiveOr`  | `Xor`  |
| `& (binary)`  | `op_BitwiseAnd`  | `BitwiseAnd`  |
| `|`  | `op_BitwiseOr`  | `BitwiseOr`  |
| `&&`  | `op_LogicalAnd`  | `And`  |
| `||`  | `op_LogicalOr`  | `Or`  |
| `=`  | `op_Assign`  | `Assign`  |
| `<<`  | `op_LeftShift`  | `LeftShift`  |
| `>>`  | `op_RightShift`  | `RightShift`  |
| `N/A`  | `op_SignedRightShift`  | `SignedRightShift`  |
| `N/A`  | `op_UnsignedRightShift`  | `UnsignedRightShift`  |
| `==`  | `op_Equality`  | `Equals`  |
| `!=`  | `op_Inequality`  | `Equals`  |
| `>`  | `op_GreaterThan`  | `CompareTo`  |
| `<`  | `op_LessThan`  | `CompareTo`  |
| `>=`  | `op_GreaterThanOrEqual`  | `CompareTo`  |
| `<=`  | `op_LessThanOrEqual`  | `CompareTo`  |
| `*=`  | `op_MultiplicationAssignment`  | `Multiply`  |
| `-=`  | `op_SubtractionAssignment`  | `Subtract`  |
| `^=`  | `op_ExclusiveOrAssignment`  | `Xor`  |
| `<<=`  | `op_LeftShiftAssignment`  | `LeftShift`  |
| `%=`  | `op_ModulusAssignment`  | `Mod`  |
| `+=`  | `op_AdditionAssignment`  | `Add`  |
| `&=`  | `op_BitwiseAndAssignment`  | `BitwiseAnd`  |
| `|=`  | `op_BitwiseOrAssignment`  | `BitwiseOr`  |
| `,`  | `op_Comma`  | `Comma`  |
| `/=`  | `op_DivisionAssignment`  | `Divide`  |
| `--`  | `op_Decrement`  | `Decrement`  |
| `++`  | `op_Increment`  | `Increment`  |
| `- (unary)`  | `op_UnaryNegation`  | `Negate`  |
| `+ (unary)`  | `op_UnaryPlus`  | `Plus`  |
| `~`  | `op_OnesComplement`  | `OnesComplement`  |

### Overloading Operator ==

Overloading `operator ==` is quite complicated. The semantics of the operator need to be compatible with several other members, such as [Object.Equals](https://learn.microsoft.com/en-us/dotnet/api/system.object.equals).

### Conversion Operators

Conversion operators are unary operators that allow conversion from one type to another. The operators must be defined as static members on either the operand or the return type. There are two types of conversion operators: implicit and explicit.

❌ DO NOT provide a conversion operator if such conversion is not clearly expected by the end users.

❌ DO NOT define conversion operators outside of a type’s domain.

For example, [Int32](https://learn.microsoft.com/en-us/dotnet/api/system.int32), [Double](https://learn.microsoft.com/en-us/dotnet/api/system.double), and [Decimal](https://learn.microsoft.com/en-us/dotnet/api/system.decimal) are all numeric types, whereas [DateTime](https://learn.microsoft.com/en-us/dotnet/api/system.datetime) is not. Therefore, there should be no conversion operator to convert a `Double(long)` to a `DateTime`. A constructor is preferred in such a case.

❌ DO NOT provide an implicit conversion operator if the conversion is potentially lossy.

For example, there should not be an implicit conversion from `Double` to `Int32` because `Double` has a wider range than `Int32`. An explicit conversion operator can be provided even if the conversion is potentially lossy.

❌ DO NOT throw exceptions from implicit casts.

It is very difficult for end users to understand what is happening, because they might not be aware that a conversion is taking place.

✔️ DO throw [System.InvalidCastException](https://learn.microsoft.com/en-us/dotnet/api/system.invalidcastexception) if a call to a cast operator results in a lossy conversion and the contract of the operator does not allow lossy conversions.

_Portions © 2005, 2009 Microsoft Corporation. All rights reserved._

_Reprinted by permission of Pearson Education, Inc. from[Framework Design Guidelines: Conventions, Idioms, and Patterns for Reusable .NET Libraries, 2nd Edition](https://www.informit.com/store/framework-design-guidelines-conventions-idioms-and-9780321545619) by Krzysztof Cwalina and Brad Abrams, published Oct 22, 2008 by Addison-Wesley Professional as part of the Microsoft Windows Development Series._

## See also

  * [Member Design Guidelines](member.md)
  * [Framework Design Guidelines](index.md)

_源站标注：Last updated on 2021-09-15_
