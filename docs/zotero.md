# Zotero Integration

## Ownership boundary

| Concern | Authority |
| --- | --- |
| Bibliographic metadata, collections, tags, deduplication | Zotero |
| PDFs and other attachments | Zotero |
| Zotero notes and PDF annotations | Zotero |
| Citation and bibliography formatting | Zotero/CSL |
| Paper analysis, verified claims, gaps, and project relevance | ResearchFlow |
| Links from papers to observations, hypotheses, experiments, runs, and decisions | ResearchFlow |

ResearchFlow never writes to Zotero and never copies a Zotero PDF. `rf evidence zotero show` reads the current item, attachment, note, and annotation context for an agent or human. Only `link` creates a ResearchFlow record, and that record contains a source pointer plus an empty analysis template.

## Prerequisites

1. Install and start Zotero Desktop.
2. In Zotero Settings > Advanced, enable **Allow other applications on this computer to communicate with Zotero**.
3. Do not forward or expose port `23119`. Zotero local reads are intentionally unauthenticated.

The integration uses the official Local API at `http://127.0.0.1:23119/api`, API version 3. Official documentation: [Local API](https://www.zotero.org/support/dev/web_api/v3/local_api) and [Web API basics](https://www.zotero.org/support/dev/web_api/v3/basics).

## Configure and verify

```powershell
rf evidence zotero configure --library users/0
rf evidence zotero status
rf evidence zotero libraries
rf evidence zotero collections
```

`configure` records `authority: zotero` and `access: read_only` in the global ResearchFlow preferences. It does not connect to Zotero; `status` is the connectivity check.

## Zotero-owned retrieval

```powershell
rf evidence zotero search "visual navigation" --limit 25
rf evidence zotero search "diffusion policy" --collection ABCD1234 --tag core
rf evidence zotero show ITEMKEY
rf evidence zotero bibliography ITEMKEY OTHERKEY --style apa --locale en-US
```

- Search uses Zotero quick search with `qmode=everything`, so Zotero's local full-text index performs the retrieval.
- `show` returns the bibliographic item and reads child attachments, standalone notes, attachment annotations, and Zotero's current `file://` attachment URL without persisting them or copying the file.
- `bibliography` delegates CSL formatting to Zotero and prints the returned HTML.

Group libraries use `--library groups/<numeric-id>`. `libraries` reports the available personal and group-library identifiers.

## Handoff into ResearchFlow analysis

```powershell
rf evidence zotero link ITEMKEY
# returns PAPER-0001

rf evidence paper show PAPER-0001
rf evidence zotero refresh PAPER-0001
```

`link` is idempotent for the same Zotero database/library/item tuple. It writes:

```text
evidence/papers/analysis/PAPER-0001.md  analysis plus source frontmatter
evidence/papers/index.jsonl            compact retrieval index
```

It does not write `evidence/papers/pdf/PAPER-0001.pdf`. `refresh` updates only the bibliographic frontmatter/index snapshot and preserves the analysis body.

## Failure meanings

- **Cannot reach Local API**: Zotero is stopped or the local API preference is disabled.
- **403**: enable the Zotero local API preference.
- **Database identity differs**: Zotero is serving a different database/profile; review the source before relinking.
- **Manual PDF copying is disabled**: add/manage the item in Zotero, then use `link`.
