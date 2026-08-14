# GPU sidecar for the local Darija STT engine (benchmark/stt_server.py).
#
# Why this image is not `python:3.11-slim` like api/Dockerfile: this process is
# the one part of the system that needs torch + CUDA. Putting it in the API
# image would add ~8 GB to a service that has no GPU and would still run on CPU
# at 60-180 s per voice note. The split is the same one documented in
# api/app/providers/local_darija.py — that adapter is a thin HTTP client, this
# is the thing it calls.
#
# Why the weights are NOT baked in with a COPY: the checkpoint is 5.8 GB and its
# largest shard is 4.7 GB. Baking it would make this image unbuildable on any
# machine that has not already downloaded it, and it cannot be fetched from git
# either — 4.7 GB exceeds GitHub's 2 GB Git-LFS per-file ceiling. The weights
# are bind-mounted from benchmark/models/ by docker-compose.yml; the catalogue
# that reproduces them (download_models.py) is what lives in version control.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# ffmpeg is not optional: run_local.load_audio falls back to it for Ogg/Opus,
# which is the format Telegram and WhatsApp voice notes actually arrive in.
# libsndfile1 backs soundfile. --no-install-recommends keeps the layer small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch/torchaudio come from the base image, so requirements-local.txt (which
# deliberately omits torch — it needs the CUDA index URL) installs cleanly here.
# --only-binary :all: refuses sdists, so no dependency can run a setup script at
# build time; requirements-local.txt is pinned exactly, so the same commit
# always resolves to the same wheels. Same posture as api/Dockerfile, minus the
# hashes — see the header of requirements-local.txt for why they cannot apply
# here.
COPY requirements-local.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements-local.txt \
    && groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Only the two modules the sidecar imports (stt_server pulls WhisperRunner and
# load_audio from run_local, which imports nothing else local). Copying all of
# benchmark/ would drag the dataset and results into the build context for no
# reason.
COPY --chown=appuser:appuser stt_server.py run_local.py ./

# Unprivileged from here on: port 8100 needs no privilege, the weights are
# mounted read-only, and the only path the process writes is a temp file per
# request. HF_HOME is pointed at the user's own home because the default
# (~/.cache) is root's and would be unwritable after the switch.
ENV HF_HOME=/home/appuser/.cache/huggingface
USER appuser

EXPOSE 8100

# 0.0.0.0, unlike the 127.0.0.1 default of the CLI: inside a container the
# loopback interface is the container's own, so binding there would make the
# service unreachable from the api service that needs it. It is still not
# published to the host in docker-compose.yml, so the exposure is compose-
# internal only — same posture as the api service itself.
CMD ["python", "stt_server.py", "--host", "0.0.0.0", "--port", "8100"]
