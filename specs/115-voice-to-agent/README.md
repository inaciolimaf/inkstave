# Spec 115 — Speak to the agent (prompt)

Add a microphone to the agent panel: speech becomes text through the browser's own speech recognition (Web
Speech API, on-device when the browser offers it), the user sees and can correct the transcript, and it is sent
as a normal agent message. The agent's rule does not change: it proposes, the user reviews. Read `spec.md`,
then implement it with its tests.

Depends on 46 and 110. Read the agent section of `docs/system/frontend.md` first.
