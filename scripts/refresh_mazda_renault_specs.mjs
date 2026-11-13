import * as sync from './mazda_renault_spec_sync.mjs';
import { runTechnicalRefresh, reportFailure } from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/mazda_renault_specs_intake.py',
  defaultOutput:'data/local/release-data/mazda-renault-quality-2026-11-13/specs'}).catch(reportFailure);
