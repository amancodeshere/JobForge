## Scope and modes

Home is Persuade. Demo, sign-in and the personal workspace are Operate.

## Audience and task

Australian job seekers upload a readable CV, set their own role and eligibility
preferences, search current sources and inspect a ranked shortlist. Provider
provenance, original listings and grounded drafts remain visible. Demonstration
data belongs exclusively to `/demo`.

## Direction

Extend the existing Opportunity Front identity: mineral paper, deep slate,
eucalyptus actions, Barlow Condensed display and ruled evidence ledgers. Home
owns the monumental language front. The workspace replaces its marketing hero
and wide search rail with compact headings, a 280px account rail and a guided
CV → Preferences → Results journey. The upload is the first primary task;
results take precedence after a successful search. Filtering and sorting help
users find a specific result without changing the underlying ranking evidence.

## Constraints and remaining integration

Keep the existing search, application drafting, evidence and download behavior.
Use native Streamlit OIDC, with explicit local personal mode for loopback use.
Do not imply durable account storage: the persistence layer remains separate.
Real provider credentials and the deployment callback must be configured before
hosted login works. Preserve responsive layouts, visible focus and reduced motion.
