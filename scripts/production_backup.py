"""Read-only PostgreSQL dump; only age-encrypted output may leave the runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit, parse_qs

PROJECT = 'eutcryxbitudllcnpnex'
CA_HASH = '807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
ROOT = Path(__file__).resolve().parents[1]


def connection(value):
    url = urlsplit(value)
    if (url.scheme != 'postgresql' or url.hostname != 'aws-1-eu-west-2.pooler.supabase.com'
            or url.port != 5432 or unquote(url.username or '') != 'postgres.' + PROJECT
            or url.path != '/postgres' or not url.password or url.fragment
            or parse_qs(url.query) != {'sslmode': ['verify-full']}):
        raise ValueError('Unexpected backup database target')
    password = unquote(url.password)
    if any(c in password for c in '\r\n\0'):
        raise ValueError('Invalid password encoding')
    return url, password


def run(args, env, *, input=None):
    result = subprocess.run(args, env=env, input=input, capture_output=True, timeout=600)
    if result.returncode:
        # Server errors can contain data, connection details or SQL. Never echo them.
        raise RuntimeError('Backup command failed: ' + Path(args[0]).name)
    return result.stdout


def preflight_sql():
    return ("BEGIN READ ONLY; SELECT json_build_object('read_only',current_setting('transaction_read_only')='on',"
            "'tls',(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),"
            "'version',current_setting('server_version_num')::int/10000,"
            "'news_safe',(SELECT count(*)=1 AND bool_and((NOT enabled AND NOT publication_enabled) OR "
            "(enabled AND publication_enabled AND model='gpt-6-sol' AND daily_article_limit=1 "
            "AND ((daily_limit_micro_usd=250000 AND monthly_limit_micro_usd=5000000) OR "
            "(daily_limit_micro_usd=500000 AND monthly_limit_micro_usd=10000000)))) FROM public.news_ai_config WHERE id='production'),"
            "'news_enabled',(SELECT enabled FROM public.news_ai_config WHERE id='production'),"
            "'notices_off',(SELECT count(*)=1 AND bool_and(NOT enabled) FROM public.news_notice_release_config WHERE id='production')); ROLLBACK;")


def create_backup(value, recipient, output, *, env=None):
    url, password = connection(value)
    if not re.fullmatch(r'age1[0-9a-z]{58}', recipient or ''):
        raise ValueError('Expected one age X25519 public recipient')
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Refusing to overwrite backup')
    ca = ROOT / 'database/certs/supabase-root.crt'
    # The pinned public CA is not a secret; validate DER rather than PEM newlines.
    import ssl
    if hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca.read_text())).hexdigest() != CA_HASH:
        raise ValueError('Unexpected database CA')
    with tempfile.TemporaryDirectory(prefix='eba-backup-') as tmp:
        tmp = Path(tmp)
        passfile = tmp / 'pgpass'
        escape = lambda s: s.replace('\\', '\\\\').replace(':', '\\:')
        passfile.write_text(':'.join(map(escape, [url.hostname, '5432', 'postgres',
                                                unquote(url.username), password])) + '\n')
        passfile.chmod(0o600)
        # Do not inherit PGDATABASE/PGSERVICE/PGPASSWORD or other caller overrides.
        child_env = {k: v for k, v in (env or os.environ).items() if not k.startswith('PG')}
        child_env.update(PGHOST=url.hostname, PGPORT='5432', PGUSER=unquote(url.username),
                         PGDATABASE='postgres', PGPASSFILE=str(passfile), PGSSLMODE='verify-full',
                         PGSSLROOTCERT=str(ca), PGCONNECT_TIMEOUT='20',
                         PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=300000 -c lock_timeout=10000',
                         PGAPPNAME='Elbilsagenten-scheduled-readonly-backup')
        check = run(['psql', '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-c', preflight_sql()], child_env)
        state = json.loads(check)
        if (any(state.get(k) != v for k, v in dict(read_only=True, tls=True, version=17,
                news_safe=True, notices_off=True).items()) or type(state.get('news_enabled')) is not bool):
            safe = {k: state.get(k) for k in ('read_only', 'tls', 'version', 'news_safe', 'notices_off')}
            raise RuntimeError('Backup preflight or approved news boundary failed: ' + json.dumps(safe))
        version = run(['pg_dump', '--version'], child_env).decode()
        if not re.search(r'PostgreSQL\) 17\.', version):
            raise RuntimeError('PostgreSQL 17 client required')
        dump = tmp / 'database.dump'
        roles = tmp / 'roles-no-passwords.sql'
        run(['pg_dump', '--no-password', '--format=custom', '--no-publications',
             '--no-subscriptions', '--file', str(dump)], child_env)
        roles.write_bytes(run(['pg_dumpall', '--no-password', '--roles-only', '--no-role-passwords'], child_env))
        toc = run(['pg_restore', '--list', str(dump)], child_env)
        if dump.stat().st_size < 1024 or b'canonical_models' not in toc or b'news_articles' not in toc:
            raise RuntimeError('Incomplete backup archive')
        if re.search(rb'\bPASSWORD\s+(?!NULL)', roles.read_bytes(), re.I):
            raise RuntimeError('Unexpected role credential in archive')
        manifest = dict(format='elbilsagenten-pg17-age-v1', project=PROJECT,
                        created_at=datetime.now(timezone.utc).isoformat(), source_writes=0,
                        news_enabled=state['news_enabled'], ai_calls=0, archive_list_verified=True,
                        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (dump, roles)},
                        excludes=['role passwords', 'external Storage files', 'hosting secrets',
                                  'Cloudflare D1', 'replication subscriptions/publications', 'PITR'],
                        full_restore_rehearsal=False)
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        bundle = tmp / 'backup.tar.gz'
        with tarfile.open(bundle, 'w:gz') as tar:
            for name in ('database.dump', 'roles-no-passwords.sql', 'manifest.json'):
                tar.add(tmp / name, arcname=name)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            run(['age', '--encrypt', '--recipient', recipient, '--output', str(output), str(bundle)], child_env)
            if not output.read_bytes().startswith(b'age-encryption.org/v1\n'):
                raise RuntimeError('Backup encryption failed')
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return dict(ok=True, encrypted=True, bytes=output.stat().st_size,
                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(), source_writes=0,
                    paid_calls=0, full_restore_rehearsal=False)


if __name__ == '__main__':
    try:
        print(json.dumps(create_backup(os.environ.get('BACKUP_DATABASE_URL', ''),
                                      os.environ.get('BACKUP_AGE_RECIPIENT', ''),
                                      'backup-output/database.tar.gz.age')))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, (RuntimeError, ValueError))
                          else 'Backup failed; private diagnostics suppressed', 'secrets_printed': False}))
        raise SystemExit(1)
