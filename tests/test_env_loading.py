import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from supabase_client import load_local_env


class EnvLoadingTests(unittest.TestCase):
    def test_bom_local_precedence_and_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.local').write_text('OPENAI_API_KEY="test-only"\nSHARED=local\n', encoding='utf-8-sig')
            (root / '.env').write_text('SHARED=base\nOTHER=value\n', encoding='utf-8')
            with patch('supabase_client.ROOT', root), patch.dict(os.environ, {'OTHER': 'existing'}, clear=True):
                load_local_env()
                self.assertEqual(os.environ['OPENAI_API_KEY'], 'test-only')
                self.assertEqual(os.environ['SHARED'], 'local')
                self.assertEqual(os.environ['OTHER'], 'existing')
                self.assertFalse(any(key.startswith('\ufeff') for key in os.environ))


if __name__ == '__main__': unittest.main()
