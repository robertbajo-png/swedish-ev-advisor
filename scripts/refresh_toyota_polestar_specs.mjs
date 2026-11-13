import * as sync from './toyota_polestar_spec_sync.mjs';
import { runTechnicalRefresh, reportFailure } from './refresh_kia_specs.mjs';
runTechnicalRefresh({ sync, collector: 'scripts/toyota_polestar_specs_intake.py',
  defaultOutput: 'data/local/release-data/toyota-polestar-quality-2026-11-13/specs' }).catch(reportFailure);
