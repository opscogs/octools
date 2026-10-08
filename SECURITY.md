# Security policy

Version: **1.0.0** · Date: 2026-10-08

## Supported versions

Security fixes go to the latest 1.x minor release of both packages, which are released together at one version:

| Package                  | Supported        |
| ------------------------ | ---------------- |
| `octools` (PyPI)         | latest 1.x minor |
| `@opscogs/octools` (npm) | latest 1.x minor |

Older minors and pre-1.0 releases do not receive fixes; upgrade to the latest 1.x release.

## Reporting a vulnerability

Do not open a public issue for a security problem.

1. Open the **Security** tab of this repository and choose **Report a vulnerability** (GitHub private vulnerability reporting).
2. If you cannot use that form, email `support@opscogs.com` with "octools security" in the subject.

Include the affected package and version, a description of the impact, and the smallest input or steps that reproduce it. Do not include credentials or data that is not yours.

## What to expect

These are intentions, not guarantees:

- We aim to acknowledge a report within 5 business days.
- We aim to confirm or decline the report, with a reason, within 14 days of acknowledging it.
- For a confirmed issue we aim to ship a fix in a patch release of both packages within 90 days, sooner for a severe one, and to publish a GitHub security advisory crediting the reporter unless you ask us not to.
- We ask that you keep the report private until a fix is released or we agree on a disclosure date.

## Scope

In scope: the code in this repository and the packages published from it. Out of scope: vulnerabilities in your own tool providers, in the MCP or model SDKs that consume `octools` output, and in third-party dependencies (report those to their maintainers).
