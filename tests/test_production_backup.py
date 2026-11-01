import importlib.util
from pathlib import Path
import subprocess
import json
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/production_backup.py'
spec = importlib.util.spec_from_file_location('backup', PATH)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
VALID = 'postgresql://postgres.eutcryxbitudllcnpnex:synthetic%3Apass@aws-1-eu-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full'


class BackupTests(unittest.TestCase):
    def fixture_run(self, args, env, *, input=None):
        self.assertNotIn('PGPASSWORD', env)
        self.assertFalse(any('synthetic:pass' in str(a) for a in args))
        if args[0] == 'psql':
            self.assertIn('-q', args)
            sql = args[-1]
            # Supavisor ignores PGOPTIONS for this setting; explicit SQL is required.
            return json.dumps(dict(read_only='BEGIN READ ONLY;' in sql, tls=True,
                                   version=17, news_safe=True, news_enabled=False, notices_off=True)).encode()
        if args[:2] == ['pg_dump', '--version']:
            return b'pg_dump (PostgreSQL) 17.11\n'
        if args[0] == 'pg_dump':
            Path(args[-1]).write_bytes(b'PGDMP' + b'x' * 2048)
            return b''
        if args[0] == 'pg_dumpall':
            return b'CREATE ROLE synthetic_role;\n'
        if args[0] == 'pg_restore':
            return b'TABLE public canonical_models\nTABLE public news_articles\n'
        if args[0] == 'age':
            Path(args[args.index('--output') + 1]).write_bytes(b'age-encryption.org/v1\n' + b'x' * 2048)
            return b''
        self.fail('Unexpected command')

    def test_complete_mock_pipeline_uses_explicit_readonly(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, 'run', self.fixture_run):
            result = backup.create_backup(VALID, 'age1' + 'q' * 58, Path(folder) / 'backup.age')
            self.assertTrue(result['encrypted'])
            self.assertEqual(result['source_writes'], 0)
            self.assertFalse(result['full_restore_rehearsal'])

    def test_failed_security_check_creates_no_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'backup.age'
            for change in [dict(tls=False), dict(news_safe=False), dict(notices_off=False),
                           dict(version=18), dict(news_enabled=None), dict(read_only=False)]:
                state = dict(read_only=True, tls=True, version=17, news_safe=True,
                             news_enabled=False, notices_off=True)
                state.update(change)
                with patch.object(backup, 'run', return_value=json.dumps(state).encode()) as mock:
                    with self.assertRaisesRegex(RuntimeError, 'preflight'):
                        backup.create_backup(VALID, 'age1' + 'q' * 58, output)
                    self.assertEqual(mock.call_count, 1)
                    self.assertFalse(output.exists())

    def test_approved_active_news_does_not_stop_readonly_backup(self):
        def active(args, env, **kwargs):
            value = self.fixture_run(args, env, **kwargs)
            if args[0] == 'psql':
                state = json.loads(value)
                state['news_enabled'] = True
                return json.dumps(state).encode()
            return value
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, 'run', active):
            self.assertTrue(backup.create_backup(VALID, 'age1' + 'q' * 58,
                                                Path(folder) / 'backup.age')['ok'])

    def test_exact_connection(self):
        url, password = backup.connection(VALID)
        self.assertEqual(url.port, 5432)
        self.assertEqual(password, 'synthetic:pass')

    def test_wrong_targets_and_weak_tls_rejected(self):
        for old, new in [('eutcryxbitudllcnpnex', 'anotherproject'),
                         ('verify-full', 'require'), ('5432', '6543'),
                         ('/postgres?', '/other?'), ('postgresql:', 'http:'),
                         ('pooler.supabase.com', 'attacker.example'),
                         ('synthetic%3Apass', '%0Aunsafe')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                backup.connection(VALID.replace(old, new))
        for suffix in ['&sslmode=disable', '&options=-c+default_transaction_read_only=off', '#unsafe']:
            with self.assertRaises(ValueError):
                backup.connection(VALID + suffix)

    def test_errors_do_not_print_server_body(self):
        with patch.object(backup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'PASSWORD private row')):
            with self.assertRaisesRegex(RuntimeError, '^Backup command failed: pg_dump$'):
                backup.run(['pg_dump'], {})

    def test_no_plaintext_upload_or_source_restore(self):
        source = PATH.read_text()
        self.assertIn('default_transaction_read_only=on', source)
        self.assertIn("PGSSLMODE='verify-full'", source)
        self.assertIn("'--no-role-passwords'", source)
        self.assertIn("['pg_restore', '--list'", source)
        self.assertNotIn("'--clean'", source)
        self.assertIn('TemporaryDirectory', source)
        self.assertIn("'age', '--encrypt'", source)
        self.assertIn('NOT enabled AND NOT publication_enabled', source)
        for guard in ["model='gpt-6-sol'", 'daily_article_limit=1',
                      'daily_limit_micro_usd=250000', 'monthly_limit_micro_usd=5000000']:
            self.assertIn(guard, source)


if __name__ == '__main__':
    unittest.main()
