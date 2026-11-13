import * as sync from './mercedes_cla_spec_sync.mjs';
import { runTechnicalRefresh, reportFailure } from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/mercedes_cla_specs_intake.py',
  defaultOutput:'data/local/release-data/mercedes-cla-quality-2026-11-13/specs'}).catch(reportFailure);
