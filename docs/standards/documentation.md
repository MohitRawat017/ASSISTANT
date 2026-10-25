# Documentation Standards

**Question this document answers:** What are the rules for writing and maintaining this knowledge base?

## Core Principle

Every document answers exactly **one question**, stated as the first line
under its title. If a second question needs answering, it belongs in a new
or different document, not appended here.

## No Duplication Rule

- Information lives in exactly one place.
- If a topic is relevant to multiple documents, the non-owning document links
  to the owning one instead of repeating content.
- Before adding a paragraph, check whether it already belongs to an existing
  document. If so, edit that document instead.

## Structure Every Document Must Have

1. Title (`#`)
2. One-line bolded statement of the question it answers
3. Body, organized under clear `##` headings
4. A "Related Documents" section linking outward, not inward duplication

## Style Rules

- Write for both a new engineer and an AI agent with no prior context
- Prefer tables and lists over prose paragraphs where structure helps scanning
- No marketing language, no filler sentences, no unexplained acronyms
  (define first use in [../glossary.md](../glossary.md))
- Keep documents short; if a document exceeds roughly one screen of scrolling
  per subtopic, split it

## Placeholders

- Use `[bracketed text]` for content that must be filled in with real,
  project-specific details before this document is considered complete.
- A document with placeholders is not yet authoritative; do not treat
  bracketed content as a real decision.

## Adding a New Document

1. Confirm the question it answers isn't already owned elsewhere.
2. Place it in the correct folder (`architecture/`, `standards/`, `product/`,
   `decisions/`).
3. Link it from any document that references its topic.

## Decision Records

- Architectural or process decisions with lasting consequence get an entry
  in [../decisions/](../decisions/), not inline explanation elsewhere.

## Related Documents

- Repository layout: [../architecture/folder-structure.md](../architecture/folder-structure.md)
- Term definitions: [../glossary.md](../glossary.md)