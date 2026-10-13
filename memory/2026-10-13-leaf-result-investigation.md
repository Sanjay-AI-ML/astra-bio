# Leaf screening result investigation

- Symptom: user saw “No reliable leaf match” and believed the custom model stopped working.
- Confirmed: Render loads plantdoc-20261011T142833Z, model SHA256 97c02d8fb1cefc994f59d52da3b8215545d23e7d3d3cffc18e8d536842e71e51. Same bundled reference photograph gives identical local and hosted predictions; tentative healthy score 0.9813294974083459. This is a transport/inference smoke check, not independent accuracy validation.
- Root cause of confusing display: uncertain predictions and checks were collapsed, while the title suggested no result. Inference and threshold code were unchanged in the recent summary change. Original submitted leaf photograph was not provided, so its exact uncertainty cannot be reproduced from the result screenshot.
- Fix: uncertain view says “Model prediction needs review”, directly shows unconfirmed matches and scores, expands the reasons and shows loaded model identity. Species-conflict condition names stay withheld. No threshold, weights, calibration or automatic treatment change.
- Regression evidence: PlantOverview tests cover visible uncertain matches, model identity, expanded checks and rejected species. Local and hosted API smoke inference matched exactly.
- Status: DONE_WITH_CONCERNS — display fixed and model operation verified; original user image still needed to evaluate that specific prediction. Hosted visual review not performed.
