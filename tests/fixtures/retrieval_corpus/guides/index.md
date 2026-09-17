---
title: "Reviewer Guide"
source_url: "https://example.invalid/guides/reviewer-guide"
section: "guides"
---

# Reviewer Guide

Every change must be reviewed before it is merged, and the reviewer must be able to
explain what was checked.

## Checklist

- design
- functionality
- tests
- naming
- documentation

## Samples

The code fence below contains a line that starts with "#": it is a comment inside a
code block, not a heading, and the chunker must not split the block on it.

```python
# NOT-A-HEADING: this comment lives inside a code fence.
def handler(order, repository):
    return repository.save(order)
```

## Notes

First notes section. Keep changes small so the reviewer can find five minutes.

## Notes

Second notes section carrying the marker DUP-MARKER so tests can tell the two
identically titled sections apart.

## Appendix

## After Appendix

The appendix heading above has no body: zero-width sections must be skipped and
counted rather than becoming empty chunks.
