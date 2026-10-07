# Design: The Lenny Growth Assistant

## 1. Design Principles

The application should feel like a polished AI workspace rather than a basic demo.

Core principles:

- **Grounded and trustworthy:** The UI should make it clear when answers are transcript-based.
- **Fast and focused:** Chat is the primary interaction.
- **Artifact-native:** Generated Markdown, HTML, and UI snippets deserve dedicated space.
- **Model-aware:** Users should understand whether they are using Cloud or Local inference.
- **Graceful under failure:** Offline Ollama, missing keys, and empty context should be understandable, not cryptic.

## 2. Layout Overview

The frontend uses a three-panel workspace inspired by ChatGPT and Claude.

```text
┌───────────────┬───────────────────────────────┬──────────────────────────────┐
│ Sidebar       │ Chat                          │ Artifact Viewer              │
│ Sessions      │ Messages + Composer           │ Markdown / HTML Preview      │
└───────────────┴───────────────────────────────┴──────────────────────────────┘
```

Use shadcn/ui `ResizablePanelGroup` for the desktop layout:

- Panel 1: Sidebar.
- Panel 2: Chat.
- Panel 3: Artifacts, conditionally expanded when an artifact exists.

## 3. Component Architecture

```text
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── app-shell.tsx
│   ├── session-sidebar.tsx
│   ├── chat/
│   │   ├── chat-panel.tsx
│   │   ├── chat-header.tsx
│   │   ├── message-list.tsx
│   │   ├── message-bubble.tsx
│   │   ├── chat-composer.tsx
│   │   └── model-selector.tsx
│   ├── artifacts/
│   │   ├── artifact-panel.tsx
│   │   ├── artifact-tabs.tsx
│   │   ├── markdown-artifact.tsx
│   │   └── html-artifact.tsx
│   └── status/
│       ├── model-status-badge.tsx
│       └── empty-state.tsx
├── lib/
│   ├── api.ts
│   ├── artifact-parser.ts
│   ├── types.ts
│   └── utils.ts
└── hooks/
    ├── use-sessions.ts
    ├── use-chat.ts
    └── use-model-status.ts
```

## 4. shadcn/ui Components

Required shadcn/ui components:

- `ResizablePanelGroup`, `ResizablePanel`, `ResizableHandle`
- `Sidebar`
- `ScrollArea`
- `Card`
- `Button`
- `Textarea`
- `Select`
- `Badge`
- `Separator`
- `Skeleton`
- `Tooltip`

Additional helpful components:

- `Alert`
- `DropdownMenu`
- `Tabs`
- `Toast` or `Sonner`

## 5. Sidebar UX

The sidebar follows a ChatGPT-style mental model.

### Contents

- Product name: **Lenny Growth Assistant**.
- New chat button.
- Session history list.
- Optional small status footer.

### Session Item Behavior

- Displays generated title or fallback such as `New conversation`.
- Shows relative creation/update time.
- Active session has a distinct background and left border/accent.
- Hover state reveals subtle affordances.

### Empty State

If no sessions exist:

```text
No conversations yet.
Start by asking a question about Lenny's Podcast.
```

## 6. Header UX

The chat header contains:

- Current session title.
- Model selector dropdown.
- Model health indicator.

### LLM Toggle

Use a styled `Select` with options:

- Cloud: Gemini or OpenAI, selected with CLOUD_PROVIDER in backend/.env.
- Local: Ollama llama3.2:3b.

### Status Indicator

`GET /api/models` drives availability states.

Cloud status:

- Green: selected cloud provider's API key configured (not a live quota or authentication check).
- Red: missing API key.

Local status:

- Green: Ollama reachable and `llama3.2:3b` installed.
- Yellow: Ollama reachable but required model missing.
- Red: Ollama offline.

UX copy examples:

- `Gemini key configured` / `OpenAI key configured`
- `Missing Gemini key` / `Missing OpenAI key`
- `Ollama online`
- `llama3.2:3b not found`
- `Ollama offline`

## 7. Chat Interface

The central panel is optimized for conversational flow.

### Message List

Use `ScrollArea` for smooth scrolling.

Message types:

- User message: right or full-width aligned with user styling.
- Assistant message: left/full-width with Markdown rendering.
- Error message: distinct destructive/amber styling.

### Composer

Composer requirements:

- Multiline `Textarea`.
- Send button.
- Keyboard shortcut: `Enter` to send, `Shift+Enter` for newline.
- Disabled while request is in flight.
- Placeholder examples:
  - `Ask about growth, activation, retention, or product strategy...`
  - `Ask for a Ship30for30 essay from Lenny's Podcast insights...`
  - `Ask for a Markdown or HTML artifact...`

### Loading State

When waiting for a response:

- Show assistant bubble skeleton or typing indicator.
- Keep user message visible immediately.
- Disable duplicate sends.

## 8. Artifact Viewer

The artifact viewer is the product polish centerpiece.

### Trigger

The backend may return assistant text containing XML-style artifact blocks:

```xml
<artifact type="markdown">
# Example
...</artifact>
```

or:

```xml
<artifact type="html">
<!doctype html>
...</artifact>
```

The frontend parser must:

1. Detect artifact tags.
2. Extract artifact type and content.
3. Strip the artifact block from the visible chat bubble.
4. Store the artifact in client state.
5. Expand the artifact panel automatically.

### Resizable Panel Layout

Use:

```tsx
<ResizablePanelGroup direction="horizontal">
  <ResizablePanel defaultSize={18} minSize={14}>
    <SessionSidebar />
  </ResizablePanel>
  <ResizableHandle />
  <ResizablePanel defaultSize={artifact ? 42 : 82} minSize={30}>
    <ChatPanel />
  </ResizablePanel>
  {artifact ? (
    <>
      <ResizableHandle />
      <ResizablePanel defaultSize={40} minSize={25}>
        <ArtifactPanel />
      </ResizablePanel>
    </>
  ) : null}
</ResizablePanelGroup>
```

### Markdown Artifacts

Render with `react-markdown`.

Recommended styling:

- `prose prose-neutral dark:prose-invert`
- Card-like preview container.
- Copy button.
- Optional raw/source toggle.

### HTML/CSS Artifacts

Render inside a sandboxed iframe.

Requirements:

- Use `sandbox` attribute.
- Prefer `srcDoc` over writing into the frame manually.
- Keep iframe isolated from parent app.
- Provide raw code view for inspection.

Example:

```tsx
<iframe
  title="Generated artifact preview"
  sandbox="allow-scripts"
  srcDoc={artifact.content}
  className="h-full w-full rounded-md border bg-white"
/>
```

If scripts are not required, use a stricter sandbox value.

## 9. Artifact Panel States

### Empty

```text
No artifact yet.
Ask for a UI, HTML page, Markdown brief, or code sample.
```

### Markdown Artifact

- Header: `Markdown Artifact`
- Actions: Copy, View Source.
- Body: rendered Markdown.

### HTML Artifact

- Header: `HTML Artifact`
- Actions: Copy, View Source, Refresh Preview.
- Body: sandboxed iframe preview.

### Unsupported Artifact

If an unknown artifact type appears:

- Render as escaped code.
- Show warning badge: `Unsupported preview type`.

## 10. Visual Design Direction

### Theme

- Clean neutral palette.
- Excellent dark mode compatibility.
- Subtle borders and shadows.
- Strong typography hierarchy.

### Spacing

- Sidebar width: approximately 260-320px.
- Chat max content width: approximately 760-860px.
- Composer fixed at bottom with safe padding.
- Artifact panel uses full height.

### Message Styling

Assistant responses:

- Markdown enabled.
- Comfortable line height.
- Bullets and bold text should be highly legible.

User messages:

- Slightly stronger background.
- Clear ownership.

## 11. Error and Edge States

### Backend unavailable

Show:

```text
Unable to reach the backend. Make sure FastAPI is running on port 8000.
```

### Ollama offline

Show red status and, if user selects Local:

```text
Ollama is offline. Start Ollama locally and make sure llama3.2:3b is installed.
```

### Missing cloud provider key

Show:

```text
Cloud mode needs GEMINI_API_KEY or OPENAI_API_KEY for the selected CLOUD_PROVIDER.
```

### No RAG context

The assistant should say it cannot answer from the transcripts rather than hallucinating.

### Request timeout

Show retry affordance:

```text
The model took too long to respond. Try again or switch models.
```

## 12. Accessibility

- Keyboard accessible sidebar and model selector.
- Visible focus rings.
- Sufficient contrast in light and dark modes.
- `aria-label` on icon-only buttons.
- `title` on iframe.
- Do not rely on color alone for model status; include text labels.

## 13. Mobile Behavior

The primary target is desktop for the take-home assignment, but mobile should degrade gracefully.

Recommended behavior:

- Sidebar collapses behind a trigger.
- Artifact panel becomes a tab or drawer.
- Chat remains the default view.

## 14. Product Polish Checklist

- Smooth session switching.
- Clear new chat behavior.
- Sticky composer.
- Auto-scroll to newest message.
- Artifact auto-open.
- Copy buttons for generated content.
- Model status updates on load and manual refresh.
- Friendly empty states.
- No raw XML artifact tags visible in chat bubbles.
