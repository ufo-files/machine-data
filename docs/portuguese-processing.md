# Portuguese-first Brazil processing

This repository stores Portuguese as the canonical machine text for
`Brazil-Government-UAP`. English is a paired, visibly machine-generated
derivative. Originals remain immutable in the data archive.

## Processing boundary

The authoritative archive lives on `ufo-files-agent-0` under
`/srv/ufo-files-downloads`. The Mac worker follows the established SSH
orchestrator lifecycle:

1. Read the Brazil source manifest and atomically claim one candidate.
2. Copy that one original into a job-specific directory on the external Mac
   scratch volume.
3. Verify the staged byte count and SHA-256 against the source manifest.
4. OCR or transcribe in Portuguese, then translate each canonical segment.
5. Upload all artifacts to a claim-specific temporary directory on the Pi.
6. Verify every uploaded SHA-256 and atomically publish the complete pair.
7. Record completion or retry state and remove only the job-owned scratch.

The worker does not crawl the corpus locally, alter originals, or publish a
partially uploaded pair. Three failures quarantine a source. Claims expire
after six hours so an interrupted job is resumable.

## Output contract

For an original such as:

```text
originals/Brazil-Government-UAP/Camara-dos-Deputados/RIC-3515-2018/report.pdf
```

the worker publishes:

```text
transcripts/Brazil-Government-UAP/paired/
└── Camara-dos-Deputados/RIC-3515-2018/report/
    ├── document.json
    ├── pt-BR/
    │   ├── canonical.json
    │   └── canonical.txt
    ├── en/
    │   ├── translation.json
    │   └── translation.txt
    ├── entities.json
    ├── events.json
    ├── provenance.json
    ├── qa.json
    └── review.json
```

`document_id` is derived from the source manifest's canonical identifier.
Page IDs derive from document ID and page number. Segment IDs derive from the
document ID and page/position (or media timestamps), never translated text.
Portuguese and English therefore share IDs even if a translation fails.

`entities.json` and `events.json` use canonical segment IDs as their counting
key. English evidence can add an alias or excerpt to the same occurrence but
cannot create a second count. `document_origin_country` is distinct from
`event_location`; a Brazilian record does not imply that its event occurred in
Brazil.

## Dependencies

Install the established macOS tools with Homebrew:

```sh
brew install tesseract-lang ocrmypdf poppler ffmpeg
```

`tesseract-lang` supplies `por`; both `por` and `eng` must be visible in
`tesseract --list-langs`. `ocrmypdf` uses Tesseract for scanned PDFs, Poppler
extracts born-digital page text, FFmpeg/ffprobe validates media, and the
existing `mlx-whisper` runtime transcribes Portuguese. Translation uses the
Apple-Silicon MLX runtime in an isolated virtual environment:

```sh
python3 -m venv "/Users/$USER/Library/Application Support/ufo-files/portuguese-worker/.venv"
"/Users/$USER/Library/Application Support/ufo-files/portuguese-worker/.venv/bin/pip" \
  install --requirement requirements-macos.txt
```

The default translation model is `mlx-community/aya-expanse-8b-4bit`.
Production config pins `translation_model_revision` to model commit
`3a7cee37dd4ab4ed76642f61f6253da4748e63ba`, the exact revision used by the
pilot. The Whisper model is likewise pinned to commit
`49e6aa286ad60c14352c404340ded53710378a11`. Provenance records both models,
their revisions, the `mlx-whisper` runtime version, the translation prompt
workflow version and hash, MLX runtime version, generated time, source-text
hash, Python/platform details, and OCR/transcription tool versions.

Check dependencies without processing:

```sh
python3 scripts/process_portuguese.py \
  --source /dev/null \
  --relative-path unused \
  --source-manifest /dev/null \
  --output-root /tmp/unused \
  --work-root /tmp/unused \
  --check-dependencies
```

## Translation safeguards

The source title, filename, accession code, official identifier, source URLs,
and hashes are copied as metadata and never sent for translation. Within text,
filenames, official-code patterns, coordinates, and redaction/illegibility
markers are replaced with deterministic placeholders and restored exactly.

Every paired segment is checked for names, dates, numbers, measurements,
coordinates, Portuguese negation, and redaction/illegibility markers. A
mismatch changes the status to `needs-review`; a translator error produces an
explicit failed segment and a partial/failed document status. Machine output
is never labeled reviewed automatically.

`OVNI` remains in Portuguese text and entity aliases. Its normal English
rendering is `UFO` or `unidentified flying object`, without implying an
extraterrestrial origin.

## Bounded pilot

Run the worker only with exact manifest paths while `enabled` remains `false`:

```sh
"$HOME/Library/Application Support/ufo-files/portuguese-worker/.venv/bin/python" \
  "$HOME/Library/Application Support/ufo-files/portuguese-worker/scripts/portuguese_ssh_worker.py" \
  --config "/Users/$USER/Library/Application Support/ufo-files/portuguese-worker/config.json" \
  --pilot \
  --allow-relative-path 'PATH/TO/ONE-SOURCE.pdf' \
  >> "$HOME/Library/Logs/ufo-files/portuguese-worker.log" 2>&1
```

Repeat that command for one scanned PDF, one born-digital PDF, one meaningful
image, and one audio/video source when the source archive contains one. The
current worker processes one claim per invocation regardless of allowlist
length. Validate a staged or checked-out output tree with:

```sh
python3 scripts/check_portuguese_outputs.py PATH/TO/transcripts/Brazil-Government-UAP/paired
```

Manually compare `pt-BR/canonical.txt`, `en/translation.txt`, `qa.json`, and
`review.json` before enabling scheduled work.

Record a reviewed segment (and optionally a corrected English text file) with
an auditable reviewer, timestamp, hashes, and note:

```sh
python3 scripts/review_portuguese_translation.py PATH/TO/PAIRED/DOCUMENT \
  --segment-id seg-0123456789abcdef01234567 \
  --decision reviewed \
  --reviewer review-team \
  --note 'Names, dates, quantities, negation, and uncertainty checked.'
```

Review decisions update the English derivative, document/provenance status,
remaining-review count, and `translation-reviews.json`; canonical Portuguese
is never changed.

For a model/workflow update, regenerate only derived files from the checked
canonical Portuguese and leave both the archived original and canonical bytes
untouched:

```sh
python3 scripts/retranslate_portuguese.py PATH/TO/PAIRED/DOCUMENT \
  --translation-model mlx-community/aya-expanse-8b-4bit \
  --translation-model-revision 3a7cee37dd4ab4ed76642f61f6253da4748e63ba
```

Whole-document reprocessing carries `translation-reviews.json` forward as an
audit trail, while newly generated English segments return to an unreviewed or
needs-review state; a prior approval is never silently applied to new text.

## LaunchAgent safety and operations

The template runs once daily at 02:35 and each invocation processes at most
one source. It has no `KeepAlive` loop. Default config is disabled, limits a
source to 2 GiB, requires 20 GiB free scratch, uses two OCR workers at 300 DPI,
caps the process at 12 GiB soft/16 GiB hard resident memory, and owns only
`/Volumes/OCR & Transcripts 2/.ufo-portuguese-worker`. Launchd also runs it as
a background process at nice level 10 with low-priority I/O.

Install the worker, isolated Python environment, config, and unloaded plist:

```sh
python3 scripts/install_portuguese_worker.py --config-from /path/to/reviewed-config.json
```

The installer intentionally does not call `launchctl`; merely installing the
plist cannot start a corpus run.

Enable only after the bounded pilot passes and `enabled` is deliberately set
to `true`:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.ufo-files.portuguese-worker.plist"
launchctl enable "gui/$(id -u)/com.ufo-files.portuguese-worker"
```

Monitor all worker output in one terminal (the existing verbose transcription
runtime may include transcript text):

```sh
launchctl print "gui/$(id -u)/com.ufo-files.portuguese-worker"
tail -n 100 -F \
  "$HOME/Library/Logs/ufo-files/ssh-orchestrator.log" \
  "$HOME/Library/Logs/ufo-files/portuguese-worker.log"
```

The two-file `tail` is the unified live view for the existing archive OCR/media
worker and the Portuguese OCR/transcription/translation worker. File headers
retain worker provenance while presenting one chronological terminal stream.

Rollback/disable is non-destructive:

```sh
launchctl disable "gui/$(id -u)/com.ufo-files.portuguese-worker"
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.ufo-files.portuguese-worker.plist"
```

That stops scheduling but leaves remote originals, completed derivatives,
failure state, configuration, and scratch available for audit or resumption.
