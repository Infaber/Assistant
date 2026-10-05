# Ariana

This repository contains two sibling projects:

- `ariana/`: the Python LiveKit agent, with Gemini voice and browser/search tools.
- `frontend/`: the Next.js voice and chat interface.

## Talk in the terminal

From the repository root:

```sh
cd ariana
uv sync --locked
uv run playwright install webkit
cp -n .env.example .env.local
```

Fill in `ariana/.env.local` with your `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY`. `GEMINI_API_KEY` is also accepted.
The Google key is separate from your LiveKit credentials. Save the file before
starting the agent. The copy command preserves an existing environment file.

With the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/)
installed, run:

```sh
lk agent console
```

## Use the frontend

From `ariana/`, run the worker and keep that terminal open:

```sh
lk agent dev
```

In a second terminal, from the repository root:

```sh
cd frontend
npm ci
cp -n .env.example .env.local
```

Fill in `frontend/.env.local` with the same three LiveKit values. The Google key
belongs in the agent's environment file. Then run:

```sh
npm run dev
```

Open the exact URL printed by this command. If port 3000 is occupied, Next.js
chooses another port such as 3001. Click **Start conversation**, allow microphone
access, and say hello. Text mode lets you send a message without using the mic.

Restart a running process after changing its environment file. A missing Google
key prevents the agent from responding; a missing LiveKit value prevents a
connection. Keep both `.env.local` files private and out of Git.

See the [agent guide](ariana/README.md) and [frontend guide](frontend/README.md)
for tests, deployment, and configuration options.
