# Scenario inventory

| Dimension | Required behavior |
| --- | --- |
| Input | Exact entity IDs; names must correspond; no empty/duplicate binding |
| UI | Picker chips retain requested entity type and ID |
| Wire | Entity-reference slot matches chips before any billed request continues |
| Ack | Null acknowledgement is not success, failure or a record |
| Attribution | Match project and uniquely proven new workflow, not first UUID |
| Concurrency | Old jobs and concurrent unrelated jobs cannot become our result |
| State | Started callback records IDs before terminal wait/download |
| Time | Bounded waits; report uncertain billed outcome without resubmission |
| Failure | Named safety/credit failures remain distinct from selector drift |
| Schema | Accept measured classic and alternate VIDEO record shapes only |
| Resources | Retain profile lease; clean observers/routes without killing other pages |
| Compatibility | Ordinary T2V/I2V/local R2V and image entity refusal unchanged |
| MCP parity | Entity IDs/names survive queue codec and execute the repaired path |

Critical browser scenarios: existing saved Characters produce exact entity chips and a
matching blocked wire request (free); one approved MCP run yields an attributed terminal
clip (paid). Offline scenarios cover missing/wrong/duplicate entity slots, null ack,
wrong project, stale workflow, ambiguity, no-CAE VIDEO records and timeout cleanup.
