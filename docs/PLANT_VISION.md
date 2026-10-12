# Local plant screening

The application now supports versioned local fine-tuned models. The first completed PlantDoc run is selected for experimental screening: 41.25% accuracy on 80 held-out source images, versus 28.75% for original weights. This is limited performance, not tray validation. See [the completed fine-tuning note](ML_FINE_TUNING.md) for the exact split, per-class report, abstention coverage and reproduction/switching commands. The remaining text documents the original base artifact and its smoke check.

Real ONNX MobileNetV3 artifacts come from [imaflower/plantvillage-mobilenetv3](https://huggingface.co/imaflower/plantvillage-mobilenetv3), pinned revisiond76fe187be1c4c3a5474f835a7a70cd08c7ab085. The upstream card declaresMIT. Graph, external weights, mapping, training configuration and card have pinnedSHA256 checks. Explicit setup: scripts/setup-plant-model.ps1. Inference never downloads artifacts.

ONNX RuntimeCPU:RGB, resize shorter edge256px bilinear, center-crop224px, NCHWfloat32 /255, ImageNet mean/std. Fifteen classes cover tomato, potato and bell pepper. Unsupported crops are rejected.

Species conflicts and weak/ambiguous rankings abstain. Global softmax scores are not renormalized by species or treated as correctness probabilities. Photos remain in memory; invalid/oversized/tiny/animated/flat inputs are rejected. This is not a general leaf detector; unfamiliar nonleaf images can score highly.

Actual local smoke inference on an attributed PlantVillage tomato sample gave a tentative healthy visual match with global score0.912459. It may be an upstream training sample: this verifies inference, not independent accuracy. Sample attribution:Mohanty, Hughes and Salathé2016, [DOI10.3389/fpls.2016.01419](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2016.01419/full), reportedCC-BY-SA3.0. PROVENANCE.json retains pinned source/hash and unchanged-download attribution.

No pathogen confirmation, treatment, removal, replanning or device command occurs automatically. Spaceflight/hydroponic-light/new-tray performance needs separate validation. Runtime artifacts and smoke report are Git-ignored.

Explanations recompute saved daily solver facts. Optional local Ollama selects existing fact IDs; visible statements remain verified sentences. Timeout/invalid selection falls back deterministically. No daemon/model is installed or required.
