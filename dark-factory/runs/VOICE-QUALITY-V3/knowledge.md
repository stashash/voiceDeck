# Local Factory Knowledge

- Read the Dark Factory role guidance in C:/Users/Admin/dev/project/dark-factory/skills and knowledge before coding. knowledge/recent.md is absent there; do not create or alter global factory state.
- Preserve repo conventions. React/Vite/TypeScript frontend; Vert.x/Java audio; FastAPI/Python designer.
- Generated-deck and component editors use different document schemas. Preserve both; do not silently promise parity.
- Existing fast commands bypass LLM. Keep stale-model result protection and local-only model inference.
- Existing synthetic audio acceptance is 5/9, not human accuracy. Physical microphone acceptance is absent.
- The root checkout is dirty stas; edit only this isolated worktree. Other agents have disjoint write scopes. Never revert another agent's work.
- Main integrates and commits selected files after verification; workers report changed paths and commands, never git add -A.
