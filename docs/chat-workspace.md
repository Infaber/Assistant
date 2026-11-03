# Conversation messaging

The Conversation button opens a full chat workspace within Ariana. It shares the existing session transcript, so typed messages, voice transcripts and attachment messages remain together. The home orb and diagnostics retain their layout.

The composer stays visible after sending. Enter sends; Shift+Enter inserts a line break. Drafts and staged attachments survive switching between home and chat because both views use the same composer. Sending is disabled until the existing agent is ready. Offline users can connect with text without enabling the microphone. Connection errors remain visible in chat.

Messages follow the latest response while the reader is at the bottom. Scrolling up keeps their reading position and reveals a Latest messages button. Copy transcript and tool activity remain available. Conversation history remains scoped to the existing session; this change does not add a persistent conversation database.

Validated with frontend typecheck, production build, unit tests and WebKit checks. The new browser scenarios exercise two consecutive typed exchanges with a synthetic reply transport, multiline input, draft preservation, mobile layout and silent navigation. They do not claim a live provider conversation was run.
