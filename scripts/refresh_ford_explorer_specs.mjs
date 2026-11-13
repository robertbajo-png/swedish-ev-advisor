import * as sync from './ford_explorer_spec_sync.mjs';
import {runTechnicalRefresh,reportFailure} from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/ford_explorer_specs_intake.py',
 defaultOutput:'data/local/release-data/ford-explorer-quality-2026-11-13/specs'}).catch(reportFailure);
