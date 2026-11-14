import * as sync from './kia_ev3_completion_sync.mjs';
import {runTechnicalRefresh,reportFailure} from './refresh_kia_specs.mjs';
runTechnicalRefresh({sync,collector:'scripts/kia_ev3_completion_intake.py',
 defaultOutput:'data/local/release-data/kia-ev3-completion-2026-11-14/specs'}).catch(reportFailure);
