# JobForge MCP

JobForge exposes a deliberately small Model Context Protocol surface. MCP clients can search current configured providers and prepare one evidence-grounded application without gaining filesystem, shell, environment, or demo-data access.

## Tools

### `search_jobs`

Accepts CV text, `CandidatePreferences`, and a result limit from 1 to 25. It runs live search with sample fallback disabled, validates and deduplicates listings, ranks every valid result, and returns the requested number of matches. It does not generate application copy.

Live search consumes the same provider quota as the dashboard. Australian SerpApi discovery remains one request per workflow.

### `prepare_application`

Accepts CV text, the same preferences, and one `JobResult` returned by search. JobForge revalidates the listing before producing the tailored CV, trusted LaTeX, cover letter, evidence mappings, and interview topics.

Both tools cap CV text at 200,000 characters. CV data is written only to a temporary directory for parsing and is deleted when the call finishes.

## Local stdio server

Install the locked dependencies and start the server:

```bash
uv sync --extra dev
uv run python -m jobforge_mcp.server
```

Configure an MCP client to launch that command from the repository root. A generic client entry is:

```json
{
  "mcpServers": {
    "jobforge": {
      "command": "uv",
      "args": ["run", "python", "-m", "jobforge_mcp.server"],
      "cwd": "/absolute/path/to/JobForge"
    }
  }
}
```

The exact configuration location depends on the MCP client. Local stdio inherits the process environment, so the existing provider and OpenAI variables remain available without placing credentials in MCP arguments.

## Inspect locally

Use the official MCP Inspector to verify schemas and make test calls:

```bash
npx -y @modelcontextprotocol/inspector uv run python -m jobforge_mcp.server
```

Do not use a real CV when sharing Inspector screenshots or exported logs.

## Railway remote service

Keep Streamlit and MCP as separate Railway services because Streamlit is not an ASGI server and each service binds one public port.

1. Add a second service to the existing Railway project from the same GitHub repository.
2. Name it `jobforge-mcp`.
3. Set its Railway config file path to `/railway.mcp.toml`.
4. Copy the live-search and optional OpenAI variables used by the Streamlit service.
5. Generate a high-entropy token and set it only on the MCP service:

   ```bash
   openssl rand -hex 32
   ```

   Save the result as `JOBFORGE_MCP_API_TOKEN`. Do not commit it.

6. Generate a Railway public domain. `RAILWAY_PUBLIC_DOMAIN` is automatically trusted by the MCP DNS-rebinding guard. If using a custom domain, add its hostname to `JOBFORGE_MCP_ALLOWED_HOSTS`.
7. Connect clients to `https://YOUR_DOMAIN/mcp` with `Authorization: Bearer YOUR_TOKEN`.

The unauthenticated `GET /health` endpoint reports `ready` when a token is configured and `locked` otherwise. Every MCP request fails closed when the token is absent or incorrect.

For a public multi-user service, replace the shared bearer token with OAuth before launch. The shared token is appropriate for a private, single-operator deployment only.

## Security boundaries

- MCP never reads `.env` or accepts an arbitrary CV path.
- Search is live-only; sample jobs cannot be requested through MCP.
- Remote requests require a bearer token and use constant-time comparison.
- DNS-rebinding protection allows local development, the Railway public domain, and explicitly configured hosts only.
- The request body is capped at 512 KiB and the public schemas further constrain CV and result sizes.
- Job inputs are revalidated before drafting.
- The server does not submit applications or mutate job-board accounts.
