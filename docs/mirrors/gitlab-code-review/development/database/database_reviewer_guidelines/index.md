---
title: "Database Reviewer Guidelines"
source_url: "https://docs.gitlab.com/development/database/database_reviewer_guidelines/"
section: "development/database/database_reviewer_guidelines"
fetched_at: "2026-09-16T07:45:06Z"
---

# Database Reviewer Guidelines
This page includes introductory material for new database reviewers.
If you are interested in getting an application update reviewed, check the [database review guidelines](../../database_review/index.md).
## Scope of work done by a database reviewer
Database reviewers are domain experts who have substantial experience with databases, `SQL`, and query performance optimization.
A database review is required whenever an application update [touches the database](../../database_review/index.md#general-process).
The database reviewer is tasked with reviewing the database-specific updates and making sure that any queries or modifications perform without issues at the scale of GitLab.com.
For more information on the database review process, check the [database review guidelines](../../database_review/index.md).
## How to apply for becoming a database reviewer
Team members are encouraged to self-identify as database domain experts, by adding it to their profile YAML file:
  1. Make a merge request using the [`Database reviewer` template](https://gitlab.com/gitlab-com/www-gitlab-com/-/blob/master/.gitlab/merge_request_templates/Database%20reviewer.md).
  2. Add your database expertise to your YAML file:

```
projects:
  gitlab:
    - reviewer database
```

  3. Create the merge request [using the “Database reviewer” template](https://gitlab.com/gitlab-com/www-gitlab-com/-/blob/master/.gitlab/merge_request_templates/Database%20reviewer.md).
  4. Assign to a database maintainer or the [Database Team’s Engineering Manager](https://handbook.gitlab.com/handbook/engineering/data-engineering/database-excellence/database-frameworks/).


After the `team.yml` update is merged, the [Reviewer roulette](../../code_review/index.md#reviewer-roulette) might recommend you as a database reviewer.
## Resources for database reviewers
As a database reviewer, join the internal `#database` Slack channel and ask questions or discuss database-related issues with other database reviewers and maintainers.
Get familiar with using [Database Lab from postgres.ai](https://docs.gitlab.com/development/database/database_lab/), a bot that provides developers with their own clone of the production database.
Understanding and efficiently using `EXPLAIN` plans is at the core of the database review process. The following guides provide a quick introduction and links to follow on more advanced topics:
  * Guide on [understanding EXPLAIN plans](https://docs.gitlab.com/development/database/understanding_explain_plans/).
  * [Explaining the unexplainable series in `depesz`](https://www.depesz.com/tag/unexplainable/).


We also have licensed access to The Art of PostgreSQL. If you are interested in getting access, GitLab team members can check out the issue here: `https://gitlab.com/gitlab-org/database-team/team-tasks/-/issues/23`.
Finally, you can find various guides in the [Database guides](https://docs.gitlab.com/development/database/) page that cover more specific topics and use cases. The most frequently required during database reviewing are the following:
  * [Migrations style guide](https://docs.gitlab.com/development/migration_style_guide/) for creating safe SQL migrations.
  * [Avoiding downtime in migrations](https://docs.gitlab.com/development/database/avoiding_downtime_in_migrations/).
  * [SQL guidelines](https://docs.gitlab.com/development/sql/) for working with SQL queries.
  * [Guidelines for JiHu contributions with database migrations](https://handbook.gitlab.com/handbook/ceo/office-of-the-ceo/jihu-support/jihu-database-change-process/).


## How to apply to become a database maintainer
Becoming a database maintainer uses the same process as the other projects. [Follow the general process documented here](https://handbook.gitlab.com/handbook/engineering/workflow/code-review/#how-to-become-a-project-maintainer).
For database-specific requirements, see [`Project maintainer process for gitlab-database`](https://handbook.gitlab.com/handbook/engineering/workflow/code-review/#project-maintainer-process-for-gitlab-database).
## What to do if you feel overwhelmed
Similar to all types of reviews, [unblocking others is always a top priority](https://handbook.gitlab.com/handbook/values/#global-optimization). Database reviewers are expected to [review assigned merge requests in a timely manner](https://handbook.gitlab.com/handbook/engineering/workflow/code-review/#review-turnaround-time) or let the author know as soon as possible and help them find another reviewer or maintainer.
We are doing reviews to help the rest of the GitLab team and, at the same time, get exposed to more use cases, get a lot of insights and hone our database and data management skills.
If you are feeling overwhelmed, think you are at capacity, and are unable to accept any more reviews until some have been completed, notify the merge request author with a comment on the merge request and reassign the review to another available reviewer using [Reviewer roulette](../../code_review/index.md#reviewer-roulette).
