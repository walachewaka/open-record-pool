# Backend image for open-record-pool (FastAPI + arq workers).
#
# RECONSTRUCTED from `docker history backend:latest` during the MOO-95 salvage
# (the original backend/Dockerfile was lost with the GC-deleted workdir). Layer
# order and commands mirror the running image byte-for-byte where observable.
FROM python:3.11

# System deps for audio analysis: ffmpeg (decode), libchromaprint-tools (fpcalc
# fingerprinting), libsndfile1 (soundfile/librosa), build-essential (numba/llvmlite).
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential ffmpeg libchromaprint-tools libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin"
ENV PYTHONPATH=.

COPY requirements.txt .
COPY audit-ignore.txt .
RUN pip install --upgrade pip
RUN pip install flake8
RUN pip install -r requirements.txt

# Dependency audit gate (pip-audit). Skippable with --build-arg SKIP_AUDIT=1.
ARG SKIP_AUDIT=0
RUN pip install pip-audit==2.7.3 \
    && if [ "$SKIP_AUDIT" != "1" ]; then \
         pip-audit -r requirements.txt \
           $(grep -v '^#' audit-ignore.txt | sed 's/^/--ignore-vuln /' | tr '\n' ' '); \
       fi

COPY aerich.ini ./
COPY pyproject.toml ./
COPY wait_for_db.py ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
COPY docker-entrypoint-worker.sh ./
RUN chmod +x docker-entrypoint-worker.sh

ADD migrations/ migrations/
ADD scripts/ scripts/
ADD src/ src/

# Formatting/lint gates enforced at build time (a violation breaks the build).
# E203 is ignored because black owns slice formatting and emits `a[x : y]`,
# which flake8 (wrongly, per PEP 8) calls whitespace-before-':' -- without this
# the two gates contradict each other and the build cannot pass (MOO-88; the
# conflict arrived with the MOO-81 batching helper).
RUN flake8 --ignore=E203,E501,F401,W391,E261,E402,W503 .
RUN black --check --diff .

# Music download engine tools (MOO-78): yt-dlp / scdl / spotDL run as pinned
# CLI subprocesses in their OWN venvs, never imported into the frozen app venv
# (their fast-moving, mutually conflicting deps must not touch it). /opt/tools
# stays root-owned read+exec; the app process only ever execs the binaries.
# pip-audit does NOT scan these venvs (subprocess-isolated) -- pins are refreshed
# monthly (see docs/DOWNLOADS.md / SECURITY.md item 9).
COPY tools/ ./tools/
RUN python -m venv /opt/tools/yt-dlp \
    && /opt/tools/yt-dlp/bin/pip install --no-cache-dir -r tools/yt-dlp.txt \
    && python -m venv /opt/tools/scdl \
    && /opt/tools/scdl/bin/pip install --no-cache-dir -r tools/scdl.txt \
    && python -m venv /opt/tools/spotdl \
    && /opt/tools/spotdl/bin/pip install --no-cache-dir -r tools/spotdl.txt

VOLUME ["/music"]
EXPOSE 5000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5000"]
