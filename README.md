# UFO Files Machine Data

[![Raw documents](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fufo-files%2Fmachine-data%2Fmain%2F.github%2Fbadges%2Fraw-documents.json&cacheSeconds=300)](#raw-document-count)

Machine-readable OCR and timed media transcripts from public UFO/UAP document collections. This repository is the source corpus for the [UFO Files Relationship Graph Builder](https://ufo-files.github.io/relationship-graph-builder/).

The archive preserves extracted text, transcript timing, provenance metadata, and processing-quality information in formats that can be inspected with ordinary command-line tools. It does not treat statements found in source material as verified facts.

## What is here

Each top-level collection directory contains one of two raw-document formats:

- **OCR documents** are `.txt` files. The first line is a JSON metadata record using the `ufo-files-archive-ocr/v1` schema; the remaining text is the OCR output.
- **Media transcripts** are `.tsv` files containing timed text segments. Each transcript has a `.source.json` provenance sidecar using the `ufo-files-archive-media-transcripts/v1` schema and may have a `.quality.json` assessment sidecar.

The current collections include public records from AARO, the Black Vault, the Department of Energy, the FBI, the National Archives, the NSA, WikiLeaks, and other document or media archives. Directory names preserve the collection boundary so downstream tools can retain source context.

## Raw document count

The badge counts tracked `.txt` OCR documents and `.tsv` media transcripts. It deliberately excludes:

- `.git` data and GitHub workflow files
- `.state` queues, manifests, and temporary processing output
- repository-level manifests and checksums
- `.source.json` provenance and `.quality.json` assessment sidecars
- `.DS_Store` and other non-document files

Reproduce the count locally with:

```sh
git ls-files -- '*.txt' '*.tsv' \
  ':(exclude).state/**' \
  ':(exclude)media-manifest.tsv' | wc -l
```

The `Refresh raw document badge` workflow runs after changes to `main` and updates the badge endpoint when the corpus count changes.

## Use the data

Clone the repository and work directly with the UTF-8 text and TSV files:

```sh
git clone https://github.com/ufo-files/machine-data.git
cd machine-data
```

To select only raw documents from a local checkout, use the same `git ls-files` command shown above. Consumers should validate the schema identifier before parsing a file; manifests, sidecars, and operational state are supporting data rather than additional documents.

For an interactive view of entities, evidence, relationships, maps, timelines, and tables derived from this corpus, open the [Relationship Graph Builder](https://ufo-files.github.io/relationship-graph-builder/). Its catalog records the exact machine-data commit used for every published rebuild.

## Provenance and reuse

These files are machine-generated derivatives of public source material and can contain OCR errors, transcription errors, incomplete passages, duplicated records, sensitive language, or unverified claims. Use the embedded metadata and sidecars to trace a document to its source and assess extraction quality.

Rights and reuse conditions may differ across the underlying collections. Consult the original source and its terms before redistributing source material or derived content.
