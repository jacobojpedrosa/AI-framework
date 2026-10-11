---
name: frontend-diagnose
description: Diagnose UI failures in Harness-generated React projects by correlating the frontend process, browser console/network, API responses and source.
---

Read project.yaml and run harness doctor --project PROJECT --json. Runtime
diagnosis can discover the preview's loopback web/API origins and check HTML,
assets and API contracts. A 200 HTML response does not prove that React mounted.

Use host browser tools to inspect the actual preview when available. Reuse an
existing tab with the matching origin. Correlate console/network errors with
apps/<web>/src and the declared API route; check Vite proxy/same-origin behavior
before assuming an API outage. Read bounded frontend process logs scoped to the
project. Never report tokens, request authorization headers, cookies or private
response bodies.

Remain read-only during diagnosis. Do not run npm install, alter lockfiles,
restart services or submit forms just to obtain evidence. When browser access
is unavailable, say that DOM/console behavior remains unverified; do not treat
HTTP success or source inspection as a browser test.

Give a concrete source-backed diagnosis and the next smallest check/fix.
