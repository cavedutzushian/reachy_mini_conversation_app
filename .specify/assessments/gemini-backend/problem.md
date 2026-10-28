# Problem Definition: Conversation Provider Choice

- **Slug**: gemini-backend
- **Created**: 2026-10-28
- **Inputs used**: [intake.md](intake.md) | [research.md](research.md)

## Problem Statement

The requesting Reachy Mini user cannot use their requested conversation provider within an app currently limited to Hugging Face, preventing them from pursuing that preference in their existing robot conversation workflow. This gap is raised now by the user's request; the underlying motivation, urgency, and effect on conversation outcomes remain unconfirmed. [Sources: intake; research, Users & Demand and Prior Art.]

## Affected Users & Stakeholders

- **Users**: The requesting user, who has expressed a preference the current app cannot accommodate. Wider demand has not been established. [Sources: intake; research, Users & Demand.]
- **Stakeholders**: Repository maintainers, whose maintenance burden and compatibility requirements are affected by changes to conversation behavior. No individual owner or decision-maker has been identified. [Sources: research, Evidence Against the Idea; repository instructions supplied in this conversation.]
- **Potential stakeholders, unconfirmed**: People responsible for usage charges and people whose speech or images are processed. Their identities and requirements need clarification in Q5; no separate buyer or organization is assumed. [Source: research, Data & Constraints, pricing and data use.]

## Goals

- Let the requesting user pursue their stated conversation-provider preference within their Reachy Mini workflow. This is the outcome inferred from the request; the benefit they expect remains open in Q1. [Source: intake.]
- **Proposed outcome, unconfirmed**: Preserve the robot interactions the user considers essential when exercising that preference. The research identifies existing conversation capabilities, but does not establish which are essential to this user; see Q3. [Source: research, Prior Art and Gaps & Open Questions.]
- **Proposed outcome, unconfirmed**: Make the experience usable within the user's tolerance for delays, interruptions, disconnections, cost, and data handling. Acceptable thresholds remain open in Q4 and Q5. [Source: research, Data & Constraints and Gaps & Open Questions.]

## Non-Goals

- Replacing the existing conversation experience: the request is for another option, rather than removal of the current choice. Whether the default should change remains open in Q6. [Source: intake.]
- Claiming superior conversation quality, lower latency, lower cost, or broader adoption without measurements. Research establishes none of these benefits. [Source: research, Users & Demand and Evidence Against the Idea.]
- **Proposed boundary, unconfirmed**: Improving unrelated robot behaviors or supporting additional provider preferences beyond the stated request. Confirm the initial scope in Q3. [Source: intake; scope boundary inferred from the single requested addition.]

## Success Metrics

Only the unmet provider preference is established. The following measures translate it into assessable outcomes; proposed measures and targets need confirmation before they become acceptance criteria.

| Signal | Baseline | Target / status |
| --- | --- | --- |
| Requesting user can complete their intended robot conversation using their preferred provider | Unavailable within the current app | User confirms the intended conversation can be completed; the representative scenario is unresolved in Q1 |
| Completion rate for essential conversation interactions | No measurements supplied | Proposed measure; interactions and acceptable completion rate unresolved in Q3 and Q4 |
| Response delay and time until playback stops after interruption | No comparative hardware measurements | Proposed measures; acceptable thresholds and measurement conditions unresolved in Q4 |
| Conversation continuity over the intended session duration | Desired duration and observed failure rate unknown | Proposed measure; duration and acceptable disruption unresolved in Q4 and Q5 |
| Cost of representative usage and acceptability of data handling | Usage profile, budget, and privacy preferences unknown | Proposed quantitative cost measure and qualitative acceptability check; unresolved in Q5 |

Sources: intake; research, Prior Art, Data & Constraints, and Gaps & Open Questions. No numeric performance targets or improvement claims are inferred from provider documentation.

## Cost of Inaction

The requester remains unable to exercise the stated preference within this app. Hosted Hugging Face conversations without an API key and user-managed local/LAN Hugging Face connections remain the documented alternatives. There is no supplied evidence of lost users, financial loss, or degraded conversation performance attributable to the missing choice; the magnitude of the unmet need is unknown. [Sources: intake; research, Market & Context and Evidence Against the Idea.]

## Open Questions

1. **Q1 - Need and audience**: [NEEDS CLARIFICATION: What motivates the provider preference, which real conversation scenario is blocked, who else experiences it, and why does it matter now?]
2. **Q2 - Eligibility and operating context**: [NEEDS CLARIFICATION: Which service/account environment will users rely on, and what access, region, authentication, and quota constraints apply?]
3. **Q3 - Essential outcomes and scope**: [NEEDS CLARIFICATION: Which existing interactions must work, including camera use, tools, memory, voices, languages, transcripts, interruption, personalities, and diagnostics; are unrelated behavior changes excluded?]
4. **Q4 - Experience thresholds**: [NEEDS CLARIFICATION: What completion rate, response delay, interruption delay, and tolerance for conversation disruption are acceptable on actual robot hardware?]
5. **Q5 - Usage and data expectations**: [NEEDS CLARIFICATION: What session duration, usage volume, budget, and speech/image data-handling requirements apply, and who owns those decisions?]
6. **Q6 - Existing users and setup**: [NEEDS CLARIFICATION: Should the current experience remain the default, and how much setup effort is acceptable for users choosing another provider?]
7. **Q7 - Compatibility boundary**: [NEEDS CLARIFICATION: Which supported Python versions must remain usable, given the instruction/metadata discrepancy recorded in research?]
8. **Q8 - Service assurance**: [NEEDS CLARIFICATION: What service stability and support guarantees are required, given the differing stable-model and preview-interface labels recorded in research?]

These questions carry forward the research gaps. Model identity was resolved in research; account availability, user value, and practical outcomes were not. Technical choices belong to later stages.
