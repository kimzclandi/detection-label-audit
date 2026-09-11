# Data attribution and usage

The normalized reference annotations are derived from BDD100K, Regents of the University of California, via the fixed public mirror dgural/bdd100k revision `c2e7f266756bcd07b87f1a45a35937c8eac20241`. The full upstream copyright/permission/disclaimer notice is retained in [BDD100K_LICENSE.rst](docs/BDD100K_LICENSE.rst) and applies to reference data and modifications distributed here. This is educational, non-commercial research. MIT applies only to original code.

Original source: https://github.com/bdd100k/bdd100k
License: https://github.com/bdd100k/bdd100k/blob/master/doc/source/license.rst
Mirror: https://huggingface.co/datasets/dgural/bdd100k/tree/c2e7f266756bcd07b87f1a45a35937c8eac20241

Fixed detector predictions were previously generated in kimzclandi/driving-data-engine, commit `3a0843db83812e1775bd4144aa0c2087cb34d851`, using a MobileNetV3 Faster R-CNN ROI-head checkpoint with SHA256 `93a87ed9669cc6b10cac501cfa457d534c03735aa1ec91d719b57045c6db0286`. No new neural inference or training was performed for this audit. The reference records contain derived bounding boxes and predictions for exact auditing replay, not images or model weights.

“Unmodified reference” does not mean independently confirmed error-free. Synthetic corruption ground truth is defined only by the inserted change. Real-label-error claims require independent human adjudication, which has not occurred.
