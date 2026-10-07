# Ariana backend

The Python project is `ariana-assistant`. It uses Gemini Live through LiveKit with
`gemini-3.8-live` as the configurable default, Achernar voice and British English.

Start with the [repository setup](../README.md). Detailed documentation:

- [Models, reasoning and architecture](../docs/architecture.md)
- [Integration reference](../docs/agent-reference.md)
- [Development and simulations](../docs/development.md)
- [Mac control](../docs/mac-control.md)
- [Memory](../docs/memory.md)
- [Security](../docs/security.md)

Run from this directory: `uv sync --locked`, then `lk agent console` for terminal
voice or `lk agent dev` for a frontend worker. Credentials belong in `.env.local`.
