# Indexes Module — Visual UI Design (v1 filtered)

**Date:** 2026-08-16  
**Status:** Approved for implementation (user-supplied; filtered to v1 locks)  
**Parent:** `docs/superpowers/specs/2026-08-16-index-module-v1-design.md`

> Appearance / layout only. No Consolidation / Super Index, no emoji tags, no standalone Python collector, no DROP without audit context.

## Overview layout

**Row 1 — four KPI cards (full width preferred; health ring optional secondary):**

| KPI | Label |
|-----|--------|
| 1 | Missing Index Impact |
| 2 | High Frag (>30%) |
| 3 | Dead Unused Writes (write-waste signal) |
| 4 | Duplicate Indexes |

**Row 2 — analytics strip:**

| Panel | Content |
|-------|---------|
| Per database | Issue counts by DB (existing) |
| Frag distribution | Healthy / Moderate / Critical bands — only when frag data exists; else muted empty |
| Wasted space GB | Recoverable / unused write footprint in GB |

## Script presentation

- Banner: Target + Confidence score/100 + reasons  
- Copy button only if `confidence_score >= 70`  
- Below gate: reasons only, no script payload  
- DROP scripts must include review/audit preamble (never “bare DROP”)

## Frag bands (display)

| % | Status | Action |
|---|--------|--------|
| <10 | Healthy | — |
| 10–30 | Moderate | REORGANIZE (copy) |
| >30 | Critical | REBUILD (copy) |

## Tags (no emoji)

`Unused` · `Write-heavy` · `High frag` · `Duplicate` · `Disabled` · `Heap` · `Missing`
