"""Download the Darija STT candidates into benchmark/models/.

Run with the ISOLATED venv, never api/.venv:
    .venv-local/Scripts/python.exe download_models.py --list
    .venv-local/Scripts/python.exe download_models.py
    .venv-local/Scripts/python.exe download_models.py --only whisper

Every entry was probed against the Hub API on 2026-08-07; `Morocco-Darija-STT-large-v1.6`
(the id hardcoded in api/app/providers/hf_darija.py) returned 401 and is NOT here --
it does not exist publicly, which is why that adapter has never run.
"""
import argparse
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent / "models"

# family: whisper  -> seq2seq, accepts an initial_prompt (chantier vocabulary),
#                     emits punctuation and mixed Latin/Arabic like the prod path.
#         wav2vec2 -> CTC, no prompt, no punctuation, bare characters.
#         other    -> its own runner.
# adapter: True -> LoRA weights only, needs the base model merged in first.
CATALOGUE = [
    # --- Whisper, Darija fine-tunes -----------------------------------------
    ("BounharAbdelaziz/Morocco-Darija-STT-large", "whisper", False,
     "the Moroccan-speech collection's only model, ~2B sharded"),
    ("ychafiqui/whisper-medium-darija", "whisper", False, "~769M"),
    ("ychafiqui/whisper-small-darija", "whisper", False, "~244M, 459 dl"),
    ("KandirResearch/Whisper-Small-Darija", "whisper", False, "~244M"),
    ("TaloCreations/whisper-darija-finetuned", "whisper", False, "275 dl, license unstated"),
    ("C-Ilyas/whisper-base-darija", "whisper", False, "~74M, floor of the range"),
    ("anaszil/whisper-large-v3-turbo-darija", "whisper", True,
     "LoRA adapter over whisper-large-v3-turbo, 1310 dl / 9 likes"),

    # --- wav2vec2 CTC, Darija ----------------------------------------------
    ("boumehdi/wav2vec2-large-xlsr-moroccan-darija", "wav2vec2", False,
     "most-liked Darija ASR on the Hub (29)"),
    ("amineouaki/wav2vec2-darija-combined", "wav2vec2", False, "most-downloaded (4784)"),
    ("amineouaki/wav2vec2-large-xlsr-53-darija-combined", "wav2vec2", False, "266 dl"),

    # --- Controls: same architecture, no Darija training --------------------
    # Without these a fine-tune win cannot be attributed: local decoding with an
    # initial_prompt may be doing the work, not the Darija data.
    ("openai/whisper-large-v3", "whisper", False, "CONTROL - the weights Groq serves"),
    ("openai/whisper-large-v3-turbo", "whisper", False,
     "CONTROL - base for the anaszil adapter"),

    # --- Generalist multilingual, not Darija-specific -----------------------
    ("Qwen/Qwen3-ASR-1.7B", "other", False, "modern multilingual ASR, own runner"),
]

# huggingface_hub pulls every file in the repo by default, including optimizer
# and scaler checkpoints that are pure training residue -- several GB of weights
# that inference never opens.
IGNORE = [
    # other frameworks' copies of the same weights
    "*.msgpack", "*.h5", "*.onnx", "*.tflite",
    # training residue -- inference never opens these
    "optimizer.pt", "scaler.pt", "scheduler.pt", "rng_state.pth",
    "training_args.bin", "checkpoint-*/*",
    # Hub repos ship the SAME weights in several formats. transformers loads
    # model.safetensors and ignores the rest, so pytorch_model.bin and the fp32
    # variants are pure disk burn -- openai/whisper-large-v3 pulled 18 GB where
    # 3.1 GB was needed before these three patterns were added (2026-08-07).
    "pytorch_model*.bin", "*.fp32-*", "*fp32*.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show the catalogue, download nothing")
    parser.add_argument("--only", default=None,
                        help="filter by family: whisper, wav2vec2, other")
    args = parser.parse_args()

    entries = CATALOGUE
    if args.only:
        entries = [e for e in entries if e[1] == args.only]

    if args.list:
        for repo, family, adapter, note in entries:
            tag = "ADAPTER" if adapter else family
            print(f"{tag:<9} {repo:<52} {note}")
        print(f"\n{len(entries)} entries -> {MODELS_DIR}")
        return

    from huggingface_hub import snapshot_download

    MODELS_DIR.mkdir(exist_ok=True)
    failures = []
    for i, (repo, family, adapter, note) in enumerate(entries, 1):
        target = MODELS_DIR / repo.replace("/", "__")
        print(f"\n[{i}/{len(entries)}] {repo}  ({family}{', ADAPTER' if adapter else ''})")
        try:
            snapshot_download(repo_id=repo, local_dir=str(target), ignore_patterns=IGNORE)
            size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
            print(f"    OK  {size / 1e9:.2f} GB -> {target.name}")
        except Exception as exc:  # one dead repo must not stop the batch  # noqa: BLE001
            print(f"    !! {type(exc).__name__}: {exc}")
            failures.append((repo, f"{type(exc).__name__}: {exc}"))

    print(f"\n{len(entries) - len(failures)}/{len(entries)} downloaded")
    if failures:
        print("failed:")
        for repo, err in failures:
            print(f"  {repo}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
