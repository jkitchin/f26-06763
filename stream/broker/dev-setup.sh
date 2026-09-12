#!/bin/sh
# Creates the local broker's password file and a dev config pointing at it.
# Everything it writes is gitignored: the Pi's credentials are not in the repo
# and neither are yours.
set -e
here=$(cd "$(dirname "$0")" && pwd)

if [ ! -f "$here/publisher.secret" ]; then
  python3 -c "import secrets;print(secrets.token_urlsafe(24))" > "$here/publisher.secret"
  chmod 600 "$here/publisher.secret"
  echo "wrote $here/publisher.secret"
fi

rm -f "$here/passwd"
mosquitto_passwd -c -b "$here/passwd" tep-publisher "$(cat "$here/publisher.secret")"

sed -e "s|/etc/mosquitto/passwd|$here/passwd|" \
    -e "s|/etc/mosquitto/acl|$here/acl|" \
    "$here/mosquitto.conf" > "$here/mosquitto.dev.conf"
echo "wrote $here/mosquitto.dev.conf"
echo
echo "start it with:  mosquitto -c $here/mosquitto.dev.conf"
