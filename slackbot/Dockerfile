# Slack bot: a small web service plus the GitLab Duo CLI it uses to talk to Duo.
FROM python:3.13-slim

# The Duo CLI is pinned to a version and its published checksum.
ARG DUO_CLI_VERSION=9.29.0
ARG DUO_CLI_SHA256=0e99a822a41afaa8a00326a2c18cfb1754e193d16b5a7fa0ed6f2a8cb43ad247

# git: checkout of the project that Duo reads. ripgrep: fast code search for Duo.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --silent --show-error --location --output /usr/local/bin/duo \
        "https://gitlab.com/api/v4/projects/46519181/packages/generic/duo-cli/${DUO_CLI_VERSION}/duo-linux-x64" \
    && echo "${DUO_CLI_SHA256}  /usr/local/bin/duo" | sha256sum --check \
    && chmod 0755 /usr/local/bin/duo

RUN useradd --create-home bot
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --requirement requirements.txt

COPY bot ./bot

USER bot
ENV HOME=/home/bot \
    WORKSPACE_DIR=/home/bot/workspace \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# One process, several threads: requests mostly wait on Slack, GitLab or Duo.
# No worker timeout, because a Duo turn can take minutes.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 bot.main:app"]
