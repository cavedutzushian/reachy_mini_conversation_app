# Concept: Optional Gemini Conversation Experience

- **Slug**: gemini-backend
- **Created**: 2026-10-28
- **Recommended option**: Option B - Bounded optional Gemini experience
- **Inputs used**: [intake.md](intake.md), [research.md](research.md), [problem.md](problem.md)

The options below are proposals. User priorities, acceptance thresholds, account access, and an agreed spending limit remain unresolved. Appetite categories are proposed budget caps for comparison, not delivery estimates or commitments; there is no evidence yet that either build option fits its proposed cap.

## Options

### Option A - Keep the current app and evaluate the preference separately

- **Sketch**: Users continue the existing Hugging Face robot conversations. The requester can assess whether Gemini's conversation experience addresses their underlying motivation outside the robot workflow before committing to an app change. Any separate trial would establish preference only; it would not establish robot compatibility or satisfy the requested in-app choice.
- **Appetite**: small (days), proposed cap for clarifying the need and evaluating preference; no app implementation budget. Trial access and any usage charges remain unconfirmed.
- **Trade-offs**: Avoids new app maintenance and preserves the documented current experience. Leaves the requested robot workflow unavailable and cannot establish performance with robot microphones, speakers, motion, or tools. Research provides no quantified cost of postponement. [Sources: problem, Cost of Inaction; research, Market & Context.]
- **Rabbit holes**: Treating a separate conversation trial as proof of robot performance; expanding preference evaluation into an unbounded provider benchmark; trying to reproduce robot behavior outside the app.

### Option B - Bounded optional Gemini experience

- **Sketch**: Users can choose Gemini for a defined robot conversation scenario while retaining the existing Hugging Face choice. The proposed smallest useful experience covers spoken conversation, interruption, personality instructions, essential robot tool use, and visible conversation transcripts. Before specification, the requester must identify the essential scenario and confirm whether camera use, memory, or other existing interactions are indispensable. Omitted capabilities must be clear to users; an omission that breaks the essential scenario makes this option insufficient.
- **Appetite**: medium (weeks), proposed budget cap pending maintainer agreement. Research identifies protocol, session, and tool-behavior differences but provides no implementation estimate or hardware evidence; feasibility within this cap is unverified. [Source: research, Prior Art and Data & Constraints.]
- **Trade-offs**: Directly addresses the requested provider choice and offers a concrete conversation outcome to assess. Limits the initial parity commitment, but requires users to accept a declared capability boundary. Account eligibility, setup burden, cost, privacy expectations, interruption quality, and conversation continuity remain risks. [Sources: problem, Goals and Success Metrics; research, Evidence Against the Idea.]
- **Rabbit holes**: Pursuing every existing setting and diagnostic before proving the essential conversation; taking on several Google service environments; expanding into model comparison or automatic provider selection; attempting to guarantee unlimited conversation continuity or lower cost without usage evidence.

### Option C - Broad parity across conversation providers

- **Sketch**: Users choose either provider and expect equivalent access to the existing conversation experience, including camera interactions, memory, personalities, voices and languages, transcripts, interruption, diagnostics, and long-session continuity. The commitment is to comparable user outcomes; identical voices or identical model responses are not assumed.
- **Appetite**: large (months), an unapproved budget category for considering a broader commitment. Neither the necessary budget nor the ability to achieve this scope has been established; this is not an estimate.
- **Trade-offs**: Reduces capability surprises and may serve users with more varied workflows. It creates a larger compatibility and maintenance obligation before demand beyond one request is demonstrated. Provider differences may prevent some expectations from being met. [Sources: problem, Q3; research, Users & Demand, Data & Constraints, and Evidence Against the Idea.]
- **Rabbit holes**: Defining parity as identical provider behavior; solving every session edge case before validating user value; adding enterprise environments, new providers, or unrelated robot improvements; committing to unmeasured quality guarantees.

## Recommendation

Recommend **Option B for the decision stage**, conditional on confirming the essential scenario, service access, and an agreed budget. It is the smallest in-app option here that directly addresses the stated preference. Option A leaves that outcome unmet, while the broader commitment in Option C is unsupported by demonstrated demand. [Sources: intake; problem, Goals; research, Users & Demand.]

Evaluate its value using the problem definition's proposed signals: completion of the intended conversation, essential interaction success, response and interruption delays, continuity over the intended duration, and acceptable cost and data handling. The thresholds remain unresolved; this recommendation establishes neither measured improvement nor readiness to implement. If indispensable interactions exceed the bounded scope or the budget cannot be agreed, revisit the option at the decision stage rather than silently expanding it.

## Out of Scope (for the recommended option)

- Replacing Hugging Face or changing the default experience. Keeping the current default is a proposed boundary, subject to problem Q6.
- Supporting multiple Google service environments, additional providers, or additional model variants in the first increment. The intended environment must be confirmed under Q2.
- Broad feature parity, continuous camera/video experiences, and new diagnostics beyond the confirmed essential scenario. Existing camera or memory use cannot be excluded if the requester identifies it as essential under Q3.
- Automatic provider switching, provider rankings, and claims of better latency, quality, or cost without measurements.
- Unrelated motion, personality-authoring, or robot-platform changes, and modifications to SDK internals. [Source for SDK compatibility constraint: repository instructions supplied in this conversation.]
- New commitments to unlimited sessions, service guarantees, or privacy assurances beyond what is verified for the chosen service and usage tier.

## Assumptions to Validate

- **User value (Q1)**: The requester has a representative robot conversation that provider choice would materially improve or enable; preference alone does not establish the benefit.
- **Access (Q2)**: One service environment can serve the intended users with acceptable account, regional, credential, and quota requirements.
- **Minimum useful scope (Q3)**: The bounded experience is useful without broad parity. The proposed core interactions and any indispensable camera or memory behavior need explicit confirmation.
- **Experience (Q4)**: Actual robot use can meet agreed response, interruption, tool-success, and disruption thresholds; no hardware evidence currently establishes this.
- **Usage and data (Q5)**: Intended session duration, charges, and speech/image data handling are acceptable to the responsible users.
- **Setup and defaults (Q6)**: Users accept optional setup and retaining the current default.
- **Compatibility and assurance (Q7-Q8)**: Supported runtime versions and required service stability can be reconciled with the chosen experience.
- **Appetite and ownership**: Maintainers accept a medium budget cap and ongoing ownership. No delivery time, funding, maintainer agreement, or issue approval is inferred from invoking this assessment stage.
