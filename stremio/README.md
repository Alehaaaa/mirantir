# Mirantir Stremio — Cloudflare Workers

Cloudflare-hosted Stremio addon with manifest.json, configure, catalog,
meta, stream, and health endpoints. This is separate from Kodi and serves an
indexed Cloudflare D1 copy of the Mirantir catalogue.

The Worker never downloads a Palantir .zm3 during Stremio navigation.
A GitHub Action reuses the Kodi palantir_source.py and catalogue_sync.py
modules to discover the current source dynamically, apply .zm3 + .upN
updates and export SQL for D1. No database repository URL is hardcoded.

## First-time setup

1. Install Node.js 22+ and log in to your Cloudflare account with Wrangler.
2. From the repository root run:

    cd stremio
    npm install
    npx wrangler login
    npx wrangler d1 create mirantir-stremio
    export CF_D1_DATABASE_ID='paste-your-D1-database-UUID-here'
    node scripts/config.mjs --production
    npx wrangler d1 migrations apply mirantir-stremio --remote --config wrangler.generated.jsonc
    npm run deploy
    openssl rand -hex 32
    npx wrangler secret put CONFIG_KEY --config wrangler.generated.jsonc
    python3 scripts/export_catalogue.py --output .data/import
    node scripts/import_d1.mjs

Paste the random value from openssl into the CONFIG_KEY secret prompt.
Never commit it to GitHub or hardcode it in the Worker.

Visit https://YOUR-WORKER.workers.dev/configure and install the generated
Stremio manifest URL. The base /manifest.json works without debrid credentials
for catalogues and metadata. Real-Debrid and AllDebrid require personal API
keys. Configured URLs contain AES-GCM encrypted tokens but remain bearer
credentials and must not be shared. Rotating CONFIG_KEY revokes old URLs.

## GitHub Actions

Add these GitHub repository secrets before merging/deploying:

- CLOUDFLARE_ACCOUNT_ID: Cloudflare account identifier
- CLOUDFLARE_API_TOKEN: token scoped for Workers and D1 editing
- CF_D1_DATABASE_ID: existing D1 database UUID
- STREMIO_CONFIG_KEY: random key of at least 32 characters

The Cloudflare workflow deploys changes pushed to main and refreshes the
catalogue at 08:00 and 20:00 UTC daily. The validation workflow performs
Worker tests and a Wrangler dry run on pull requests.

This feature branch does not deploy automatically.

## Development

    cd stremio
    npm install
    npm run config
    npx wrangler d1 migrations apply mirantir-stremio --local --config wrangler.generated.jsonc
    cp .dev.vars.example .dev.vars
    npm run dev
    npm test

Set a unique CONFIG_KEY in .dev.vars. To import a fixture database locally,
run python3 scripts/export_catalogue.py --db /path/to/moria.cm3
and then node scripts/import_d1.mjs --local.

## Modules

- src/index.js: Stremio HTTP router and configuration UI
- src/protocol.js: manifest, IDs and metadata formatting
- src/catalogue.js: indexed D1 SQL queries
- src/security.js: stateless AES-GCM credential envelopes
- src/streams.js: per-user debrid link resolution
- migrations/0001_catalogue.sql: D1 tables and indexes
- scripts/export_catalogue.py: source discovery, full+incremental sync, SQL export
- scripts/import_d1.mjs: staged import and final generation activation

Identifiers: mirantir:movie:<tmdb>, mirantir:series:<tmdb>,
and mirantir:series:<tmdb>:<season>:<episode> for episode streams.
Catalogues support search and skip extras.

D1 import only switches active_generation after successful staging.
Older generations remain for rollback and should be periodically removed.
The Worker does not proxy videos, store user API keys, or parse unsupported
.p4u files. Actual Cloudflare deployment and live debrid playback still require
account-level verification.
