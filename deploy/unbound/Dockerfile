# Unbound resolver for the sandbox (SPEC §7.2). Base image pinned by dated tag.
FROM debian:trixie-20261005-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends unbound gettext-base \
    && rm -rf /var/lib/apt/lists/* /etc/unbound/unbound.conf.d/*
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY unbound.conf.tmpl root.hints.tmpl /etc/unbound/templates/
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
