# -*- coding: utf-8 -*-
import platform

# Languages supported by prince-canuma/Kokoro-82M MLX model:
# American English (a), British English (b), French (f), Hindi (h)

flags = {"a": "🇺🇸", "b": "🇬🇧", "f": "🇫🇷", "h": "🇮🇳"}

flags_win = {"a": "american", "b": "british", "f": "french", "h": "hindi"}

voices = {
    "a": [
        "af_alloy",
        "af_aoede",
        "af_bella",
        "af_heart",
        "af_jessica",
        "af_kore",
        "af_nicole",
        "af_nova",
        "af_river",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_michael",
        "am_onyx",
        "am_puck",
        "am_santa",
    ],
    "b": [
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
        "bm_daniel",
        "bm_fable",
        "bm_george",
        "bm_lewis",
    ],
    "f": ["ff_siwis"],
    "h": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
}

if platform.system() == "Windows":
    available_voices_str = "\n".join(
        [f"  {flags_win[lang]}:\t{', '.join(voices[lang])}" for lang in voices]
    )
else:
    available_voices_str = "\n".join(
        [f"  {flags[lang]}:\t{', '.join(voices[lang])}" for lang in voices]
    )
