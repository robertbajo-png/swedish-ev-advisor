import * as sync from './cupra_born_spec_sync.mjs';
import {runTechnicalRefresh,reportFailure} from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/cupra_born_specs_intake.py',
 defaultOutput:'data/local/release-data/cupra-born-quality-2026-11-14/specs'}).catch(reportFailure);
