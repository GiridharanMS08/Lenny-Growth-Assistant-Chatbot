# Design

## Principles
- Evidence before eloquence: sources are visible next to answers.
- One primary workspace: chat is the center of the product.
- Artifacts are first-class output, not raw code dumps.
- Failure states are explicit rather than silently fabricated.
- Responsive layout collapses to chat-first on narrow screens.

## Interaction states
- Empty: prompt examples guide first action.
- Loading: composer disables and shows Thinking.
- Success: answer + sources appear.
- Artifact: rendered preview appears in Artifact Viewer.
- Error: backend failure is surfaced in the conversation.

## Accessibility
Semantic headings, keyboard-friendly textarea, readable contrast, responsive layout, and iframe title are included in the MVP.
