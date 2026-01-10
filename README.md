# Audiblez: Generate Audiobooks from E-books

![Audiblez GUI on MacOSX](./imgs/mac.png)

### 🚀 Optimized for Apple Silicon (Mac Only)

Audiblez generates `.m4b` audiobooks from regular `.epub` e-books using high-quality local AI text-to-speech models.

**This fork is heavily optimized for macOS**, utilizing [MLX](https://github.com/ml-explore/mlx) to run up to **40% faster** on Apple Silicon (M1/M2/M3) compared to standard CPU execution.

## Features

*   **Two High-Quality TTS Engines:**
    *   **Chatterbox Turbo**: Fast, expressive, and supports **Voice Cloning** (clone any voice from a 5-15s audio sample).
    *   **Kokoro-82M**: Extremely natural sounding lightweight model with support for multiple languages.
*   **Voice Cloning**: Clone your own voice or any character's voice using Chatterbox.
*   **GUI & CLI**: Comes with a user-friendly Graphical Interface and a powerful Command Line Interface.
*   **Fast Generation**: ~70+ characters/second on M2 chips. ~40 mins for a medium-sized novel.

## Installation

### Recommended: Using uv (Fastest)

[uv](https://github.com/astral-sh/uv) is a fast Python package manager.

1.  **Install dependencies:**
    ```bash
    brew install ffmpeg espeak-ng uv
    ```

2.  **Clone and set up:**
    ```bash
    git clone https://github.com/santinic/audiblez
    cd audiblez
    uv sync
    
    # Download Spacy model
    uv pip install pip
    uv run python -m spacy download xx_ent_wiki_sm
    ```

3.  **Run:**
    ```bash
    # Run the GUI
    uv run audiblez-ui
    
    # Or run the CLI
    uv run audiblez book.epub -v af_sky
    ```

## TTS Models & Voices

### 1. Chatterbox Turbo (Recommended)
Best for speed and customization. Supports **Voice Cloning**.

*   **Default Mode**: Uses a high-quality neutral English voice.
*   **Voice Cloning**: Provide a 5-15s audio file (`.mp3`, `.wav`) to clone that voice.

**GUI Voice Settings:**
*   **Exaggeration**: Controls expressiveness/emotion (Low=monotone, High=dramatic).
*   **CFG Scale**: Controls how closely it mimics the reference voice.

**Expressive Event Tags:**
Chatterbox Turbo supports emotion/sound tags that can be embedded in text for more natural expressions:

| Tag | Effect |
|-----|--------|
| `[laugh]` | Laughter |
| `[chuckle]` | Light laugh |
| `[sigh]` | Sigh |
| `[gasp]` | Gasp of surprise |
| `[cough]` | Cough |
| `[groan]` | Groan |
| `[sniff]` | Sniff |
| `[shush]` | Shushing sound |
| `[clear throat]` | Throat clearing |
| `[pause]` | Adds a pause |
| `[whisper]` | Whispered speech |

**Example:**
```
[sigh] I can't believe it's Monday again. [groan] But hey, [clear throat] let's make the best of it!
```

> **Note**: Quotation marks are automatically removed during processing to prevent the model from incorrectly vocalizing them as sighs.

### 2. Kokoro-82M
Supported languages and built-in voices:

| Language | Voices |
|----------|--------|
| 🇺🇸 American English | `af_alloy`, `af_heart`, `af_sky`, `am_adam`, `am_onyx`, ... |
| 🇬🇧 British English | `bf_alice`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis` |
| 🇫🇷 French | `ff_siwis` |
| 🇮🇳 Hindi | `hf_alpha`, `hm_omega` |

*(Note: Some languages from the original Kokoro model are not yet fully supported in this MLX port)*

## Usage

### GUI (Graphical Interface)
Simply run:
```bash
uv run audiblez-ui
```
*   Select "Chatterbox Turbo" for voice cloning.
*   Select "Kokoro" for preset voices.

### CLI (Command Line)

**Basic generation with Kokoro:**
```bash
audiblez book.epub -v af_sky
```

**Using Chatterbox with Voice Cloning:**
```bash
audiblez book.epub -e chatterbox --ref-audio my_voice.mp3
```

**Manually picking chapters:**
```bash
audiblez book.epub -p -e chatterbox
```

**Options:**
```text
  -h, --help            Show help
  -e, --engine          TTS engine: 'kokoro' (default) or 'chatterbox'
  -v, --voice           Voice ID (for Kokoro)
  --ref-audio FILE      Reference audio for cloning (Chatterbox only)
  -s, --speed           Speed multiplier (0.5 to 2.0)
  -p, --pick            Interactively select chapters
  -o, --output          Output folder
```

## Performance

On an M2 MacBook Pro:
*   **Speed**: ~70-80 chars/second
*   **Time**: "Animal Farm" (~160k chars) takes ~40 minutes.

## Resuming Interrupted Jobs

Audiblez **automatically resumes** from where it left off if generation is interrupted (crash, error, or manual stop). It detects existing chapter MP3 files and skips them.

### CLI Resume
Simply run the same command again with the **same output folder**:
```bash
audiblez book.epub -e chatterbox -o ~/Downloads/MyBook
# If interrupted, just run the exact same command again
```

### GUI Resume
1. Open the same EPUB file
2. Set **Output Folder** to the parent of your existing MP3 folder
   - If your files are in `~/Downloads/Book Title/`, set output to `~/Downloads`
3. Use the same TTS model and voice settings
4. Click **Start** — existing chapters will be skipped

> **Tip**: To regenerate a specific chapter (e.g., if it has issues), delete that chapter's MP3 file and run again.

## Author

Original by [Claudio Santini](https://claudio.uk).
Mac/MLX & Chatterbox integration by [@jarodise](https://github.com/jarodise).
Distributed under MIT license.
