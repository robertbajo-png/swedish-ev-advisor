import * as sync from './bmw_i4_spec_sync.mjs';
import {runTechnicalRefresh,reportFailure} from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/bmw_i4_specs_intake.py',
 defaultOutput:'data/local/release-data/bmw-i4-quality-2026-11-14/specs'}).catch(reportFailure);
