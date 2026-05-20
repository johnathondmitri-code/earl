# ============================================================================
# Earl Agent — E2B sandbox template
# ============================================================================
# Pre-bakes uv + Earl + all Python deps so per-workspace sandboxes boot in
# <3s instead of doing a 90s install each time.
#
# Build:
#   E2B_ACCESS_TOKEN=... e2b template create earl-agent \
#     --cmd 'sleep infinity' \
#     --ready-cmd '/home/user/earl/venv/bin/python -c "import earl_workspace"'
#
# The template is read-only at runtime. The Earl SaaS provisioner spawns a
# sandbox from this template, sets per-workspace EARL_* env vars, and
# launches `python -m gateway.run` from the pre-installed venv.
# ============================================================================

FROM e2bdev/code-interpreter:latest

# ----------------------------------------------------------------------------
# 1. System deps (apt — needs root). The base image is Debian Trixie which
#    has Python 3.12; we let uv download 3.11 in step 3 because Earl pins it.
# ----------------------------------------------------------------------------
USER root
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ffmpeg \
        ripgrep \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
USER user
WORKDIR /home/user

# ----------------------------------------------------------------------------
# 2. Install uv (Python project manager). uv can also install Python itself.
# ----------------------------------------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/user/.local/bin:${PATH}"

# Pre-download Python 3.11 via uv (saves ~30s at first venv creation)
RUN uv python install 3.11

# ----------------------------------------------------------------------------
# 3. Clone Earl Agent + pre-install all Python deps
# ----------------------------------------------------------------------------
RUN mkdir -p /home/user/earl && \
    git clone --depth 1 https://github.com/johnathondmitri-code/earl.git /home/user/earl/repo

WORKDIR /home/user/earl/repo

RUN uv venv /home/user/earl/venv --python 3.11 && \
    . /home/user/earl/venv/bin/activate && \
    uv pip install -e ".[all]" 2>&1 | tail -10

# ----------------------------------------------------------------------------
# 4. Pre-create state dirs (writable at runtime)
# ----------------------------------------------------------------------------
RUN mkdir -p /home/user/earl/logs /home/user/earl/state

# ----------------------------------------------------------------------------
# 5. Activate the venv for any shell the sandbox spawns
# ----------------------------------------------------------------------------
ENV VIRTUAL_ENV="/home/user/earl/venv"
ENV PATH="/home/user/earl/venv/bin:/home/user/.local/bin:${PATH}"

# ----------------------------------------------------------------------------
# 6. Verify the install succeeded at build time (catches broken imports early
#    and proves the whole agent surface — not just a few modules — boots in
#    the template's venv).
# ----------------------------------------------------------------------------
RUN /home/user/earl/venv/bin/python -c "\
import earl_workspace; \
import gateway; import gateway.run; import gateway.platforms.telegram; \
import agent; \
import tools; \
import providers; \
import plugins; \
import cron; \
print('Earl Agent surface imports OK')"

# ----------------------------------------------------------------------------
# 7. Verify the gateway launcher exists in the repo (catches the case where
#    scripts/start-earl.sh was removed but the template was rebuilt anyway).
# ----------------------------------------------------------------------------
RUN test -f /home/user/earl/repo/scripts/start-earl.sh && \
    echo "start-earl.sh present"

WORKDIR /home/user/earl/repo
