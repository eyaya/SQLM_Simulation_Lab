# SQLM Simulation API - FastAPI + NumPy/SciPy/Matplotlib solver
#
# Build context is ./backend; the sources land at /app/backend so that the
# app's own PROJECT_ROOT (three parents up from app/simulation.py) resolves
# to /app and ep_results sits at /app/ep_results.
FROM python:3.12-slim AS runtime

# UID/GID of the host user that owns the mounted ep_results directory.
ARG UID=1000
ARG GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first so solver edits do not invalidate the pip layer.
# numpy, scipy and matplotlib all ship manylinux wheels, so no compiler
# toolchain is needed in the image.
COPY requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY app /app/backend/app

# Run unprivileged, but with the host UID so figures written into the
# bind-mounted ep_results volume stay owned by the host user.
RUN set -eux; \
    getent group "${GID}" >/dev/null || groupadd --gid "${GID}" sqlm; \
    getent passwd "${UID}" >/dev/null || useradd --uid "${UID}" --gid "${GID}" \
        --no-create-home --shell /usr/sbin/nologin sqlm; \
    mkdir -p /app/ep_results /tmp/matplotlib; \
    chown -R "${UID}:${GID}" /app /tmp/matplotlib
USER ${UID}:${GID}

# Pre-build the font cache as the runtime user; otherwise the first plot
# request pays a several-second one-off penalty.
RUN python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; plt.figure()"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Studies are CPU-bound and can run for minutes, so keep the keep-alive
# window wide and scale with workers rather than threads.
ENV UVICORN_WORKERS=2
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers \"${UVICORN_WORKERS}\" --timeout-keep-alive 75"]
