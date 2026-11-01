import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/production_backup.py'
spec = importlib.util.spec_from_file_location('backup', PATH)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
VALID = 'postgresql://postgres.eutcryxbitudllcnpnex:synthetic%3Apass@aws-1-eu-west-2.pooler.supabase.com:5432/postgres?sslmode=verify-full'


class BackupTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
