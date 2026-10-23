#!/bin/sh
# Render unbound.conf and root.hints from templates, add one forward-zone per passthrough
# domain (SPEC §7.2, D-004), check the result, then run unbound in the foreground.
set -eu
: "${PDNS_ROOT_IP:?}" "${UPSTREAM_DNS:?}" "${CACHE_MAX_TTL:=3600}"
export PDNS_ROOT_IP UPSTREAM_DNS CACHE_MAX_TTL

templates=/etc/unbound/templates
envsubst '${PDNS_ROOT_IP}' < "$templates/root.hints.tmpl" > /etc/unbound/root.hints
envsubst '${CACHE_MAX_TTL}' < "$templates/unbound.conf.tmpl" > /etc/unbound/unbound.conf

passthrough=${PASSTHROUGH_FILE:-/etc/unbound/passthrough.txt}
if [ -f "$passthrough" ]; then
    sed -e 's/#.*//' -e 's/[[:space:]]//g' "$passthrough" | while read -r domain; do
        [ -n "$domain" ] || continue
        printf '\nforward-zone:\n    name: "%s"\n    forward-addr: %s\n' "$domain" "$UPSTREAM_DNS"
    done >> /etc/unbound/unbound.conf
fi

# Extra client networks outside RFC1918 (e.g. a VPN on 100.64.0.0/10), space separated.
for cidr in ${RESOLVER_EXTRA_ALLOW:-}; do
    printf '\nserver:\n    access-control: %s allow\n' "$cidr" >> /etc/unbound/unbound.conf
done

unbound-checkconf /etc/unbound/unbound.conf
unbound -V | head -n 1
exec unbound -d -c /etc/unbound/unbound.conf
