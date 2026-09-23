---
title: "GraphQL API merge request checklist"
source_url: "https://docs.gitlab.com/development/graphql_guide/reviewing/"
section: "development/graphql_guide/reviewing"
fetched_at: "2026-09-16T07:45:06Z"
---

# GraphQL API merge request checklist
The GitLab GraphQL API has a fair degree of complexity so it’s important that merge requests containing GraphQL changes be reviewed by someone familiar with GraphQL. You can ping one via the `@gitlab-org/graphql-experts` group in an MR or in the [`#f_graphql` channel](https://gitlab.slack.com/archives/C6MLS3XEU) in Slack (available to GitLab team members only).
GraphQL queries need to be reviewed for:
  * breaking changes
  * authorization
  * performance


## Review criteria
This is not an exhaustive list.
### Description with sample query
Ensure that the description includes a sample query with setup instructions. Try running the query in [GraphiQL](https://docs.gitlab.com/development/api_graphql_styleguide/#graphiql) on your local GDK instance.
### No breaking changes (unless after full deprecation cycle)
Check the MR for any [breaking changes](https://docs.gitlab.com/development/api_graphql_styleguide/#breaking-changes).
If a feature is marked as an [experiment](https://docs.gitlab.com/development/api_graphql_styleguide/#mark-schema-items-as-experiments), you can make breaking changes immediately, with no deprecation period.
For more information, see [deprecation and removal process](https://docs.gitlab.com/api/graphql/#deprecation-and-removal-process).
### Multiversion compatibility
Ensure that multi-version compatibility is guaranteed. This generally means frontend and backend code for the same GraphQL feature can’t be shipped in the same release.
For details, see [multiple version compatibility](https://docs.gitlab.com/development/multi_version_compatibility/).
### Technical writing review
Changes to the generated API docs require a technical writer review.
### Changelog
Public-facing changes that are not marked as an [experiment](https://docs.gitlab.com/development/api_graphql_styleguide/#mark-schema-items-as-experiments) require a [changelog entry](https://docs.gitlab.com/development/changelog/).
### Use the framework
GraphQL is a framework with many moving parts. It’s important that the framework is followed.
  * Do not manually invoke framework bits. For example, do not instantiate resolvers during execution and instead let the framework do that.
  * You can subclass resolvers, as in `MyResolver.single` (see [deriving resolvers](https://docs.gitlab.com/development/api_graphql_styleguide/#deriving-resolvers)).
  * Use the `ready?` method for more complex argument logic (see [correct use of resolver#ready](https://docs.gitlab.com/development/api_graphql_styleguide/#correct-use-of-resolverready)).
  * Use the `prepare` method for more complex argument validation (see [Preprocessing](https://graphql-ruby.org/fields/arguments.html#preprocessing)).


For details, see [resolver guide](https://docs.gitlab.com/development/api_graphql_styleguide/#writing-resolvers).
### Authorization
Ensure proper authorization is followed and that `authorize :some_ability` is tested in the specs.
For details, see [authorization guide](https://docs.gitlab.com/development/graphql_guide/authorization/).
### Performance
Ensure:
  * You have [checked for N+1s](https://docs.gitlab.com/development/api_graphql_styleguide/#how-to-see-n1-problems-in-development) and used [optimizations](https://docs.gitlab.com/development/api_graphql_styleguide/#optimizations) to remove N+1s whenever possible.
  * You use [laziness](https://docs.gitlab.com/development/api_graphql_styleguide/#laziness) appropriately.


### Frontend GraphQL fragment changes
Apply this section when an MR changes a `.graphql` file under `app/assets/`, `ee/app/assets/`, or `app/graphql/queries/`. Check the following for N+1 query risk.
  * Trace the query depth when a fragment adds a new nested association. For example, a `checkpoints` selection inside a `workflow` selection inside a list of `workflows`. Follow the full query path from the root field. Confirm each level is either paginated or batch-loaded.
  * Watch for list-of-lists patterns. A fragment used on a list type that also fetches a sub-list is a strong N+1 signal. For example, sessions to workflows to checkpoints. Each parent record issues a separate query for its children, unless the resolver batches the loads.
  * **Blocker:** Check for backend batch-loading on the new field. Look for `BatchLoader::GraphQL` in the resolver or type. Also check whether the parent resolver includes `LooksAhead` with a `preloads` or `unconditional_includes` entry for the field. If neither is present, the MR must add batch-loading before it merges.
  * **Blocker:** Check for `QueryRecorder` coverage in the matching request spec. Find the spec under `spec/requests/api/graphql/` or `ee/spec/requests/api/graphql/` that mirrors the resolver path. Look for an assertion such as `expect { ... }.not_to exceed_query_limit(N)` that covers the new field. Confirm the fixture creates more than one parent record, because a single record does not expose an N+1. If the assertion or the multi-record fixture is missing, the MR must add or fix the spec before it merges.
  * Use the performance bar or `development.log` locally to spot unexpected query counts before opening the MR.


### Use appropriate types
For example:
  * [`TimeType`](https://docs.gitlab.com/development/api_graphql_styleguide/#typestimetype) for Ruby `Time` and `DateTime` objects.
  * Global IDs for `id` fields


For details, see [types](https://docs.gitlab.com/development/api_graphql_styleguide/#types).
### Appropriate complexity
Query complexity is a way of quantifying how expensive a query is likely to be. Query complexity limits are defined as constants in the schema. When a resolver or type is expensive to call we need to ensure that the query complexity reflects that.
For details, see [max complexity](https://docs.gitlab.com/development/api_graphql_styleguide/#max-complexity), [field complexity](https://docs.gitlab.com/development/api_graphql_styleguide/#field-complexity) and [query limits](https://docs.gitlab.com/development/api_graphql_styleguide/#query-limits).
### Testing
  * Resolver (unit) specs are deprecated in favor of request (integration) specs.
  * Many aspects of our framework are outside the `resolve` method and a request spec is the only way to ensure they behave properly.
  * Every GraphQL change MR should ideally have changes to API specs.


For details, see [testing guide](https://docs.gitlab.com/development/api_graphql_styleguide/#testing).
