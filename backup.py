#!/usr/bin/env python3
"""
Script de backup automatique - lance depuis Render ou en local
Appelle /admin/backup-db toutes les 24h
"""
import urllib.request
import time
import os

SITE_URL = os.environ.get('SITE_URL', 'https://databroker229-1edb.onrender.com')
BACKUP_TOKEN = os.environ.get('BACKUP_TOKEN', 'backup-jja2026')

def run_backup():
    try:
        req = urllib.request.Request(
            f"{SITE_URL}/admin/backup-db",
            method="GET"
        )
        req.add_header("X-Backup-Token", BACKUP_TOKEN)
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = r.read().decode('utf-8')
            print(f"Backup OK: {resp[:200]}")
    except Exception as e:
        print(f"Backup erreur: {e}")

if __name__ == '__main__':
    print("Backup automatique demarre...")
    while True:
        run_backup()
        print("Prochain backup dans 24h...")
        time.sleep(86400)  # 24 heures
