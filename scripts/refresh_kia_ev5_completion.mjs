import * as sync from './kia_ev5_completion_sync.mjs';
import {runTechnicalRefresh,reportFailure} from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/kia_ev5_completion_intake.py',
 defaultOutput:'data/local/release-data/kia-ev5-completion-2026-11-14/specs'}).catch(reportFailure);
