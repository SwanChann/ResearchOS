# ADR-0004: Zotero is the literature authority

Status: accepted

## Context

Zotero already manages bibliographic metadata, collections, tags, PDFs, notes, annotations, and citation formatting. Copying those assets into ResearchFlow would create competing sources of truth and make migration, refresh, and deduplication ambiguous.

## Decision

Use Zotero Desktop as the authoritative bibliography and PDF library. ResearchFlow integrates through Zotero's official loopback Local API in read-only mode and stores only:

- a minimal bibliographic snapshot needed to identify an analysis;
- the Zotero database, library, item, and item-version reference;
- ResearchFlow analysis and evidence relationships.

The connector implements HTTP `GET` only, accepts loopback `/api` URLs only, requests no write authorization, stores no API key, and never copies Zotero PDFs, notes, or annotations into the ResearchFlow workspace.

## Consequences

- Collections, tags, attachment placement, annotation, deduplication, and citation style remain Zotero operations.
- Zotero search, attachment-file resolution, and formatted-bibliography endpoints can be invoked through `rf`, but their results are not authoritative ResearchFlow records until a bibliographic item is explicitly linked.
- Linking creates a `PAPER-*` analysis shell with a Zotero source reference and no local PDF. Refresh updates the bibliographic snapshot while preserving the analysis body.
- A different `Zotero-Server-ID` blocks refresh because local item versions and keys belong to a specific Zotero database. Older Zotero versions may not return a server ID; that weaker identity is reported rather than hidden.
- When the Zotero authority preference is enabled, the legacy manual PDF-copy command is rejected. Existing manually managed `PAPER-*` records remain readable for backward compatibility.
