#!/usr/bin/env python3
"""Daily consistent PostgreSQL dump + hard-link file snapshots; no credentials in argv.

Use PGHOST/PGPORT/PGUSER/PGPASSFILE and PGDATABASE=learn_v2. Run as a
trusted backup operator with BYPASSRLS, never as the web application role.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql

TABLES = ('tenant', 'le_project', 'le_knode', 'ktem_conversation', 'stored_file', 'job_progress', 'model_call')


def run(argv, **kwargs):
    # Child diagnostics can contain credentials/DSNs. Report operation only.
    try:
        return subprocess.run(argv, check=True, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=3600, **kwargs)
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError(f'{Path(argv[0]).name} failed') from None


def counts(conn):
    return {table: conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
            for table in TABLES}


def backup(root: Path, files: Path):
    stamp = datetime.now().strftime('%Y%m%d')
    dump = root / f'learn_v2-{stamp}.dump'
    manifest = dump.with_suffix('.json')
    snapshots = root / 'files'
    snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / stamp
    if dump.exists() or target.exists():
        raise RuntimeError('Today already has a backup; retain it and investigate before retrying')
    temporary_dump = dump.with_suffix('.dump.partial')
    temporary_files = snapshots / (stamp + '.partial')
    try:
        with psycopg.connect('') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute('SET LOCAL row_security = off')
            snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
            expected = counts(conn)
            run(['pg_dump', '-Fc', '--snapshot', snapshot, '--file', str(temporary_dump)])
        previous = sorted(p for p in snapshots.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8)
        args = ['rsync', '-a']
        if previous:
            args += ['--link-dest', str(previous[-1].resolve())]
        run([*args, str(files.resolve()) + '/', str(temporary_files) + '/'])
        # Snapshot DB and file store are not a shared atomic transaction. Keep
        # uploads/deletions quiescent during backup or accept this known window.
        temporary_files.rename(target)
        temporary_dump.rename(dump)
        manifest.write_text(json.dumps({'counts': expected, 'files': stamp}, indent=2) + '\n')
    except BaseException:
        temporary_dump.unlink(missing_ok=True)
        shutil.rmtree(temporary_files, ignore_errors=True)
        raise
    cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y%m%d')
    for old in root.glob('learn_v2-????????.dump'):
        day = old.stem.removeprefix('learn_v2-')
        if day.isdigit() and day <= cutoff:
            old.unlink()
            old.with_suffix('.json').unlink(missing_ok=True)
    for old in snapshots.iterdir():
        if old.is_dir() and len(old.name) == 8 and old.name.isdigit() and old.name <= cutoff:
            shutil.rmtree(old)
    print(f'Backup complete: {dump.name}')


def restore_drill(root: Path):
    dumps = sorted(root.glob('learn_v2-????????.dump'))
    if not dumps:
        raise RuntimeError('No completed backup')
    dump = dumps[-1]
    expected = json.loads(dump.with_suffix('.json').read_text())['counts']
    # Never accept a target DB from argv: cleanup may only drop this generated DB.
    target = 'learn_restore_' + uuid4().hex
    created = False
    try:
        with psycopg.connect('', autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(target)))
            created = True
        run(['pg_restore', '--no-owner', '--no-acl', '--exit-on-error', '--dbname', target, str(dump)])
        with psycopg.connect(dbname=target) as conn:
            conn.execute('SET LOCAL row_security = off')
            actual = counts(conn)
        if actual != expected:
            raise RuntimeError('Restore counts differ from backup snapshot')
        print('Restore drill passed: all primary table counts match')
    finally:
        if created:
            with psycopg.connect('', autocommit=True) as conn:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(target)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore-drill', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('PGDATABASE', 'learn_v2')
    root = Path(os.environ.get('LEARN_BACKUPS_ROOT', '/data/ai-learn-v2/backups'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    with (root / '.backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.restore_drill:
            restore_drill(root)
        else:
            backup(root, Path(os.environ.get('LEARN_FILES_ROOT', '/data/ai-learn-v2/files')))


if __name__ == '__main__':
    main()
