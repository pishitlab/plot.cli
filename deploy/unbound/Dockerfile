# Unbound resolver for the sandbox (SPEC §7.2). Base image pinned by tag + digest; the unbound
# package follows Debian trixie (security updates), the entrypoint logs the exact version.
FROM debian:trixie-20261005-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
RUN apt-get update \
    && apt-get install -y --no-install-recommends unbound gettext-base \
    && rm -rf /var/lib/apt/lists/* /etc/unbound/unbound.conf.d/*
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY unbound.conf.tmpl root.hints.tmpl /etc/unbound/templates/
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
