# Ariana workspace interface

The frontend now uses a responsive workspace rather than independent fixed-position controls. Desktop separates navigation/engine preferences, the voice session and recent conversation. Tablet retains two main panels; narrow screens stack content in document order, allowing short viewports to scroll without hiding voice or recovery controls.

The ink-and-sage palette, consistent panel borders, typography, spacing and visible primary voice action are defined in `frontend/app/workspace.css`. Existing attachment, transcript, voice settings, wake cancellation and session behavior remain in their original components. No dependency or backend changes are required.

Text entry is available from the message bar, “Type instead”, the conversation empty state, typing and the existing keyboard shortcut. It stays disconnected until the user connects. The composer becomes visible immediately and receives focus after React commits its open state; delaying visibility caused WebKit focus loss after dialog navigation.

Preferences have shortcuts to voice/microphone, appearance and session sections. Opening navigation, preferences or history does not publish audio or establish a connection. Engine context transfer remains an explicit opt-in.

Visual inspection covers desktop, mobile, preferences, a synthetic long transcript, text entry and a mocked permission error. The last two synthetic states are layout checks, not evidence of live voice behavior. Browser regression coverage includes silent navigation, composer focus, 320/768/1024/1440-pixel layouts, keyboard error scrolling and the existing wake/settings safeguards.
