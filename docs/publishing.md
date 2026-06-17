# Publishing to GitHub Pages

This repository is structured so the documentation can be published later with
GitHub Pages.

## Recommended Repository Shape

```text
.
├── README.md
├── docs
│   ├── index.md
│   ├── rebuild-guide.md
│   ├── architecture-and-operations.md
│   ├── builder-metrics.md
│   └── publishing.md
└── observability
    ├── README.md
    ├── start-lgtm.ps1
    ├── stop-lgtm.ps1
    ├── setup-codex-dashboards.ps1
    └── otelcol-config.yaml
```

## Before Publishing

Review for sensitive data:

```powershell
rg -n "api_key|secret|token|password|user_email|user_account_id|gmail|authorization|bearer" .
```

Expected notes:

- `password` may appear only as local Grafana `admin / admin` documentation.
- `token` may appear in public token economics docs.
- No real API keys, authorization headers, or private account IDs should be
  committed.

## GitHub Pages Setup

1. Push the repository to GitHub.
2. Open repository `Settings`.
3. Go to `Pages`.
4. Set source to `Deploy from a branch`.
5. Select the branch, usually `main`.
6. Select `/docs` as the publishing folder.
7. Save.

GitHub will publish `docs/index.md` as the site home page.

## Suggested LinkedIn/X Summary

I built a fully local observability stack for OpenAI Codex using OpenTelemetry,
Grafana LGTM, Loki, Tempo, and Prometheus-compatible metrics.

It captures Codex logs, traces, spanmetrics, and token economics locally, with
prompt logging disabled and collector-side redaction before storage.

The setup is reproducible with PowerShell scripts and includes dashboards for:

- Codex logs
- Codex traces
- Prometheus spanmetrics
- Token economics

Docs and scripts are in the repo.

## Suggested Repo Description

Local OpenTelemetry and Grafana observability for OpenAI Codex, including Loki
logs, Tempo traces, Prometheus spanmetrics, token economics, and privacy-focused
collector redaction.

## Suggested Tags

- OpenTelemetry
- Grafana
- Loki
- Tempo
- Prometheus
- OpenAI Codex
- Observability
- Developer Tools
- Local AI
- Token Economics
