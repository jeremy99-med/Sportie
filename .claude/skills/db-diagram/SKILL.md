---
name: db-diagram
description: Generate a Mermaid ER diagram of Sportie's database from the current Django models (falling back to the planned data model). Use for the Nov 5 database diagram milestone or whenever a schema diagram is requested.
---

# Database diagram

1. Source of truth:
   - If `backend/apps/*/models.py` define models, read those.
   - If they're empty, use `.claude/docs/data-model.md` and label the diagram "planned".
2. Write a Mermaid `erDiagram` with:
   - One entity per model plus `User` (from `django.contrib.auth`).
   - Key fields only: PK, FKs, and 2-4 important attributes with types.
   - Relationships using crow's-foot notation (`||--o{`, `||--||`) and a short verb label.
   - Two subgraph-like groupings marked with comments, one for the Community Game Ranker and
     one for the Video Analyzer.
3. Save it to `docs/db-diagram.md` (a Mermaid code block plus a 2-3 line legend), and show it
   to the user.
4. List any mismatches between the models and `data-model.md` so one of them can be fixed.
