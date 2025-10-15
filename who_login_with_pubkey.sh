#!/bin/bash
# 保存为 print_accepted_keys.sh

log_file="/var/log/auth.log"

grep "sshd.*Accepted" "$log_file" | while read -r line; do
    fingerprint=$(echo "$line" | grep -oE 'SHA256:[a-zA-Z0-9+/=]+')
    [[ -z "$fingerprint" ]] && continue

    echo "==> $line"

    while read -r key_line; do
        tmpfile=$(mktemp)
        echo "$key_line" > "$tmpfile"
        fp=$(ssh-keygen -lf "$tmpfile" 2>/dev/null | awk '{print $2}')
        rm "$tmpfile"

        if [[ "$fp" == "$fingerprint" ]]; then
            echo "Matched Public Key: $key_line"
        fi
    done < ~/.ssh/authorized_keys

    echo
done
