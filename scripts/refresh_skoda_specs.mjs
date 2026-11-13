import * as sync from './skoda_spec_sync.mjs';
import { runTechnicalRefresh, reportFailure } from './refresh_kia_specs.mjs';
runTechnicalRefresh({ sync, collector: 'scripts/skoda_specs_intake.py',
  defaultOutput: 'data/local/release-data/skoda-quality-2026-11-13/specs' }).catch(reportFailure);
