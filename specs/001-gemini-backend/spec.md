# Feature Specification: Optional Gemini Conversation Backend

**Feature Branch**: `feat/add-gemini-backend`

**Created**: 2026-10-28

**Status**: Draft - remediation decisions clarified; governance and design alignment pending

**Input**: User description: "Add Gemini as an optional conversation backend while retaining Hugging Face as the default. Support spoken conversation, interruption, personality instructions, essential robot tools, and transcripts. Define provider selection, setup failures, switching, disconnection, and session continuity. Explicitly agree camera and memory scope. Exclude automatic provider switching and additional providers."

## Clarifications

### Session 2026-10-28

- Q: What camera support should Gemini include? -> A: Existing on-demand snapshots; continuous visual interaction is excluded.
- Q: How should Gemini use persistent memory? -> A: Reuse existing saved memories and remember/forget behavior across providers; relevant saved memories may reach the selected provider.
- Q: Which Gemini service environment should the first release support? -> A: Gemini Developer API for a personal account; Google Cloud Vertex AI is excluded.
- Q: How should we resolve the disagreement between the constitution's Python 3.10 requirement and the package's current Python 3.11 minimum? -> A: Use Python 3.12 as the minimum supported runtime.
- Q: Should Gemini require manual retry while Hugging Face keeps its existing automatic recovery? -> A: Both providers automatically retry recoverable connection failures without switching providers.
- Q: How many automatic attempts should follow a recoverable connection failure? -> A: Retry indefinitely with increasing delays capped at 30 seconds; authentication and invalid configuration errors wait for correction.
- Q: Which voice setting should Gemini prioritize when several are available? -> A: Saved Gemini voice, then compatible personality voice, then environment setting, then Kore; an incompatible personality voice requires a valid Gemini override without editing the personality.
- Q: How long should the app wait before treating a connection operation as stalled? -> A: 15 seconds for connection plus setup acknowledgement, 5 seconds for an audio/message send, and 5 seconds for graceful close; recoverable timeouts enter automatic retry, and switching or shutdown cancels obsolete attempts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a Provider and Talk (Priority: P1)

As a robot user, I can explicitly select Gemini, complete its setup, and converse using my chosen personality while retaining access to Hugging Face.

**Why this priority**: Provider choice must deliver a working conversation without disrupting the existing default.

**Independent Test**: Start an unconfigured installation to confirm the default, then configure Gemini and complete three spoken exchanges with a selected personality.

**Acceptance Scenarios**:

1. **Given** no saved provider choice, **When** the app starts, **Then** Hugging Face remains selected and Gemini setup is not required.
2. **Given** valid Gemini setup, **When** the user selects Gemini and speaks, **Then** the robot responds audibly, follows the active personality instructions and greeting, and shows speaker-labelled transcripts.
3. **Given** Gemini is selected, **When** the app restarts, **Then** the selection persists; saved Hugging Face connection settings remain available.
4. **Given** missing or rejected credentials, unavailable service access, or an unsupported model or voice, **When** Gemini startup is attempted, **Then** the app reports the setup problem without exposing credentials, remains usable for configuration, and offers retry or manual provider selection.
5. **Given** a different personality is selected, **When** the next conversation begins, **Then** its instructions and enabled tool permissions apply rather than the preceding personality's settings.
6. **Given** Gemini voice settings from multiple sources, **When** the conversation is configured, **Then** a saved Gemini voice overrides the personality, a compatible personality voice overrides the environment setting, and the environment setting overrides Kore. If no saved override exists and the personality voice is incompatible, the app asks for a valid Gemini override without editing the personality. Hugging Face voice choices remain unchanged.

### User Story 2 - Interrupt and Use Robot Tools (Priority: P1)

As a robot user, I can interrupt a Gemini response and request enabled robot actions without losing the conversation.

**Why this priority**: Voice interaction must work with the robot rather than only provide audio chat.

**Independent Test**: Interrupt a spoken response, request a head movement and status, then inject a tool failure and continue speaking. Request a camera snapshot and verify shared memory creation, recall, and deletion across providers.

**Acceptance Scenarios**:

1. **Given** the robot is speaking, **When** the user interrupts, **Then** pending speech from the interrupted response stops and the next response addresses the new utterance without later playing the abandoned response.
2. **Given** enabled head movement, volume, status, dance/stop, and sleep tools, **When** each is requested, **Then** its existing action behavior is preserved, including actions that require no spoken follow-up.
3. **Given** a disabled tool or invalid arguments, **When** execution is requested, **Then** no unauthorized action occurs and the conversation remains usable.
4. **Given** an operational tool failure, **When** the tool returns its result, **Then** the failure is reported appropriately and a subsequent spoken exchange succeeds.
5. **Given** camera access is enabled, **When** the user requests a visual observation, **Then** Gemini can respond using an on-demand snapshot; no continuous image stream is started. If capture fails, the conversation continues with an error rather than an invented observation.
6. **Given** a fact saved through the existing memory behavior with either provider, **When** the user switches providers and asks a relevant question with memory access enabled, **Then** that fact remains available without transferring the prior live conversation.
7. **Given** a saved fact, **When** the user invokes the enabled forget behavior with either provider, **Then** the deletion follows existing memory rules and the fact is unavailable from saved memory in a fresh conversation with either provider.
8. **Given** camera or memory tool access is disabled for the active personality, **When** the corresponding action is requested, **Then** no capture or memory action occurs through that disabled tool.

### User Story 3 - Switch and Recover Predictably (Priority: P2)

As a robot user, I can change providers and recover from a lost connection while understanding whether conversation context continues.

**Why this priority**: Users need predictable recovery without overlapping sessions or duplicate robot actions.

**Independent Test**: Switch in both directions during speech and a tool call; disconnect Gemini and exercise resumed and fresh-session recovery.

**Acceptance Scenarios**:

1. **Given** an active conversation, **When** the user explicitly selects the other provider, **Then** old speech stops, the old conversation stops accepting input and new tool calls, and only the selected provider receives subsequent microphone audio.
2. **Given** an executing robot action during switching or interruption, **When** the session changes, **Then** already-started work follows existing tool cancellation behavior, unstarted work from the old session is discarded, and late results cannot trigger further actions or speech in the new session.
3. **Given** provider switching, **When** the new connection succeeds, **Then** a fresh conversation starts with the selected personality; prior-provider live conversation history is not automatically transferred; existing saved memories remain shared under the current memory rules.
4. **Given** either provider loses its connection, **When** the app detects a recoverable failure, **Then** it shows the recovery state, stops sending microphone audio to the failed session, discards pending output, and automatically retries the same provider while keeping manual retry and provider selection available.
5. **Given** retry on the same provider, **When** continuity can be restored, **Then** conversation context resumes without replaying robot actions; otherwise a fresh session is clearly announced and the user can continue.
6. **Given** failed recovery, **When** the service remains unavailable, **Then** the app stays responsive with an actionable error, continues automatic recovery with delays capped at 30 seconds, and permits manual retry or provider change. Authentication or invalid configuration failures require correction before automatic attempts continue.

### Edge Cases

- Rapid repeated provider selections must not create overlapping conversations; the latest confirmed selection governs the active connection.
- A provider outage, expired credentials, quota rejection, or service-ended session must produce a visible failure state rather than silent inactivity or provider fallback.
- A robot action whose completion is unknown after disconnect must not be automatically retried. The user must be told that its outcome is uncertain.
- Late audio, transcript updates, and tool requests from an abandoned session must not enter the new conversation.
- Changing provider with incompatible saved voice settings must offer a valid choice without silently overwriting the other provider's settings.
- Camera unavailability and memory read/write failures must be reported without inventing observations or claiming a save or deletion succeeded. Existing tool permissions remain effective for both providers.
- Partial transcripts must not be presented as completed utterances; interruption must not leave a falsely completed assistant response.
- A service that never acknowledges setup, stops accepting audio/messages, or ignores graceful close must reach the corresponding deadline without freezing configuration, retry, provider switching, or shutdown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to explicitly select either Hugging Face or Gemini through the existing configuration experience; selection MUST persist across restart.
- **FR-002**: Hugging Face MUST remain the default when no choice is saved. Its existing local/deployed choices MUST remain available, and installations not selecting Gemini MUST NOT require Gemini credentials.
- **FR-003**: Gemini MUST support bidirectional spoken conversation, speaker-labelled transcripts, active personality instructions, greeting, and permitted essential tools.
- **FR-004**: Users MUST be able to interrupt speech; abandoned output MUST NOT resume after the interruption.
- **FR-005**: Gemini MUST preserve existing behavior for enabled head movement, volume control, robot status, dance/stop, and sleep actions. On-demand camera access and shared persistent memory are also required under FR-014 and FR-015.
- **FR-006**: Tool permissions and argument validation MUST apply to Gemini. Operational tool failures MUST be logged and returned as errors while preserving the conversation.
- **FR-007**: Provider selection MUST distinguish connecting, connected, and disconnected/error states and report missing setup, rejected authentication, unavailable access, quota, and invalid model/voice choices with a corrective next step.
- **FR-008**: Switching MUST stop old speech and input before activating the new provider, retain provider-specific settings, and start a fresh conversation without transferring prior-provider live conversation history; shared saved memories remain available under FR-015.
- **FR-009**: Disconnection MUST stop use of the failed session and discard abandoned output. Both Hugging Face and Gemini MUST automatically retry recoverable connection failures indefinitely on the selected provider with increasing delays capped at 30 seconds. Manual retry and explicit provider selection MUST remain available; a manual provider change or application shutdown MUST cancel pending attempts for the previous session. Authentication or invalid configuration failures MUST await correction rather than repeat unchanged requests. Automatic provider switching is forbidden.
- **FR-010**: Same-provider retry MUST restore context when supported and available; otherwise it MUST visibly begin a fresh conversation. Application restart MUST NOT imply restoration of a prior live conversation.
- **FR-011**: Switching, retry, interruption, and duplicate delivery MUST NOT cause automatic re-execution of an already-dispatched robot action. Unknown completion MUST be reported as uncertain rather than retried.
- **FR-012**: Credentials MUST NOT appear in transcripts, logs, or displayed errors. Provider changes MUST NOT copy credentials or prior live conversation history between providers. Relevant shared saved memories MAY be supplied to the selected provider under existing memory rules; this is distinct from transferring live history. No new transcript persistence or retention behavior is introduced.
- **FR-013**: Unsupported provider-specific options MUST be identified before starting a conversation and allow correction. Gemini voice precedence MUST be saved Gemini voice, then compatible personality voice, then environment setting, then Kore. Without a saved Gemini override, an incompatible personality voice MUST prompt for a valid Gemini override rather than silently falling through or modifying the personality. A saved Gemini override MUST take precedence even when the personality voice is incompatible. Hugging Face voice resolution remains unchanged. No guarantee of identical voices or responses across providers is made.
- **FR-014**: Gemini MUST support existing on-demand camera snapshots when camera access is enabled. Continuous visual interaction is excluded. Capture failures MUST be reported without terminating the conversation or inventing visual observations.
- **FR-015**: Gemini MUST reuse the existing persistent memory shared with Hugging Face, including saved-memory recall and enabled remember/forget behavior. Existing permissions, retention, and deletion semantics MUST apply; no provider-specific memory store is introduced. Relevant saved memories may be sent to the selected provider, and this behavior MUST be explained during setup. A failed memory operation MUST NOT be reported as successful.
- **FR-016**: The initial Gemini option MUST target the Gemini Developer API for a personal account, with setup guidance and actionable errors for missing credentials or unavailable account access. Google Cloud Vertex AI is excluded.
- **FR-017**: Startup failures and connection loss MUST leave configuration and manual provider selection available; they MUST NOT terminate the application. Connection establishment plus setup acknowledgement MUST have a combined 15-second deadline, each audio/message send a 5-second deadline, and graceful close a 5-second deadline. A timed-out operation MUST stop owning input/output before recovery proceeds; close timeout MUST NOT block shutdown or a provider change. Recoverable timeouts MUST follow FR-009, and provider changes or shutdown MUST cancel obsolete attempts.

### Key Entities *(include if feature involves data)*

- **Provider Selection**: The saved choice between Hugging Face and Gemini, distinct from provider-specific connection settings.
- **Provider Settings**: The selected provider's connection, model, voice, and credential references; values for one provider must not overwrite the other's choices.
- **Conversation Session**: One provider connection with lifecycle state, active personality, enabled tool permissions, and temporary conversation context.
- **Transcript Entry**: A speaker-labelled utterance associated with a session and marked partial, completed, or interrupted.
- **Saved Memory**: A fact retained through the existing memory behavior, shared across providers with existing access and deletion rules; it is distinct from temporary live conversation history.
- **Tool Invocation**: A permitted requested action associated with its originating session and execution outcome, including uncertain completion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing default-provider acceptance scenarios continue to pass without requiring additional provider setup.
- **SC-002**: A robot trial completes 15 minutes and at least 10 spoken exchanges using the additional provider, with visible transcripts and the selected personality, without an application crash or unannounced fresh conversation.
- **SC-003**: In 10 interruption trials, abandoned speech stops within one second of interruption recognition in at least nine trials, with no later playback of the abandoned response in any trial.
- **SC-004**: Every essential action in FR-005 succeeds at least once in a robot trial; an injected action failure is followed by a successful spoken exchange without restarting the app.
- **SC-005**: Ten provider switches, including switches during speech and action execution, produce no overlapping conversations, duplicate robot actions, or transfer of prior-provider live conversation history; shared saved memories remain available as intended.
- **SC-006**: Missing setup, rejected authentication, quota rejection, invalid model/voice, and forced disconnection each leave retry and manual provider selection usable and expose no credentials. Tests with a silent service verify the combined 15-second connection/setup deadline, 5-second send deadline, and 5-second graceful-close deadline; expired sessions produce no further input/output, and configuration, switching, and shutdown remain usable.
- **SC-007**: Recovery tests for both providers demonstrate automatic same-provider retry after recoverable disconnection, continued context when restoration is available, and an explicit fresh-session indication when it is unavailable, with no replayed robot actions. Simulated prolonged outages demonstrate at least 10 consecutive automatic attempts with increasing delays capped at 30 seconds. Pending automatic attempts stop when the user explicitly changes providers or shuts down the app; authentication and invalid configuration errors produce no unchanged automatic retry.
- **SC-008**: After completing the setup guide, a human reviewer can select each provider, identify which is active, and correctly explain whether context survived switching or reconnection without developer assistance.

- **SC-009**: A robot trial produces a correct response about a visible test object from an on-demand snapshot, starts no continuous image stream, and reports an injected capture failure while allowing the next spoken exchange.
- **SC-010**: Memory trials in both switching directions demonstrate saving a fact, recalling it through the other provider, and forgetting it so it is unavailable from saved memory in fresh conversations with either provider. Injected memory failures produce no false success report.
- **SC-011**: With camera and memory tools disabled, requested captures and memory operations through those tools produce no action in all permission tests.

## Assumptions

- This is an optional backend for the existing single-robot application, not a provider marketplace. Additional providers, automatic provider switching, and provider ranking are excluded.
- Existing profiles, tool permissions, robot actions, configuration surfaces, and transcript retention remain the baseline. Provider-specific differences must be disclosed; broad feature parity is not assumed.
- The robot has working microphones, speakers, and network access. The responsible user supplies eligible service access and accepts the chosen service's usage charges and data handling; no price, quota, or privacy improvement is claimed.
- Agreed scope includes on-demand camera snapshots, existing shared persistent memory, and the Gemini Developer API for a personal account. Continuous visual interaction, provider-isolated memory, and Google Cloud Vertex AI are excluded.
- The numerical trial targets above are reviewable acceptance defaults rather than measured performance claims. Additional enabled tools must not bypass permissions or claim unsupported capabilities.
- Both providers automatically retry recoverable connection failures indefinitely with increasing delays capped at 30 seconds and without automatic provider switching. Authentication and invalid configuration errors wait for correction. Unlimited retry does not guarantee unlimited session continuity; same-provider recovery preserves context only when the service can actually restore it.
- The user-selected minimum supported runtime is Python 3.12. Align package metadata, dependency resolution, installation guidance, and minimum-runtime validation with this baseline before implementation is accepted. The conflicting Python 3.10 constitution/repository guidance and Python 3.11 package metadata require explicit follow-up updates; this clarification does not amend those files.
- Existing repository compatibility, quality, documentation, and SDK rules apply. This document authorizes no dependency addition or application implementation.
- The earlier Gemini assessment records a historical needs-clarification decision; the three scope decisions above are now resolved, but this user-requested draft does not imply maintainer approval, an agreed issue, a budget, or successful hardware validation. Those prerequisites must be settled before implementation.
