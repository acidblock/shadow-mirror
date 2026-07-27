# Shadow Mirror — Rung 1 demo container.
#
# Self-contained and reproducible: installs the engine from the LOCAL source copied
# in (no PyPI, no git auth, no network beyond the base image + pip), plus mutmut,
# then runs the demo. Build from the REPO ROOT:
#
#   docker build -f docker/Dockerfile -t shadow-mirror-demo .
#   docker run --rm shadow-mirror-demo
#
# Rung 2 (browsers for Playwright) is a base-image swap — point BASE_IMAGE at a
# trusted Playwright image and add your UI tests, e.g.:
#   docker build -f docker/Dockerfile \
#     --build-arg BASE_IMAGE=mcr.microsoft.com/playwright/python:v1.50.0-noble \
#     -t shadow-mirror-demo .
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Engine from local source (the repo is the build context) + mutmut for the contrast.
WORKDIR /src
COPY pyproject.toml README.md ./
COPY shadow_mirror ./shadow_mirror
RUN pip install --no-cache-dir '.[engine]' mutmut

# The demo sample.
WORKDIR /work
COPY examples/sample-repo /work
RUN chmod +x /work/demo.sh

CMD ["bash", "/work/demo.sh"]
