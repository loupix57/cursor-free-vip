#!/bin/sh
# Script à installer sur le nœud distant (ex. raspberry-12) pour que l'utilisateur
# pi puisse lire le Maildir/mbox d'un compte sans mot de passe (via sudo NOPASSWD).
#
# Installation sur le Pi :
#   sudo cp read-user-maildir.sh /usr/local/bin/read-user-maildir
#   sudo chmod 755 /usr/local/bin/read-user-maildir
#
# Sudoers (éditer avec sudo visudo) :
#   pi ALL=(ALL) NOPASSWD: /usr/local/bin/read-user-maildir
#
# Usage : read-user-maildir <username>
# (Le script est appelé par le script Python via : ssh pi@<host> "sudo /usr/local/bin/read-user-maildir <username>")

[ -z "$1" ] && exit 0
# Un seul argument, caractères sûrs uniquement (a-z, 0-9, _)
case "$1" in (*[!a-z0-9_]*) exit 0;; esac
u="$1"

# Maildir puis mbox
cat "/home/$u/Maildir/new/"* 2>/dev/null
cat "/var/mail/$u" 2>/dev/null
cat "/var/spool/mail/$u" 2>/dev/null
