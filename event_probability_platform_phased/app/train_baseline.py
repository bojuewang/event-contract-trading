from __future__ import annotations

"""
Baseline model training example.

Replace this synthetic example with a historical dataset built from:
- pregame/in-play odds snapshots
- score/time/play-by-play state
- injury/news features
- final result label

Recommended first production model:
- LightGBM/XGBoost for tabular live-state features, calibrated with isotonic regression.
- PyTorch GRU/Transformer only after you have enough sequence data.
"""

from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

rng = np.random.default_rng(7)
n = 50000
score_diff = rng.normal(0, 12, n)       # positive = team A ahead
minutes_left = rng.uniform(0, 48, n)
pre_game_prob = rng.beta(5, 5, n)
market_prob = np.clip(pre_game_prob + score_diff / 80 - minutes_left / 400 * rng.normal(0, 1, n), 0.01, 0.99)
logit = np.log(market_prob / (1 - market_prob)) + score_diff / 20 - minutes_left / 100
true_prob = 1 / (1 + np.exp(-logit))
y = rng.binomial(1, true_prob)
X = np.column_stack([score_diff, minutes_left, pre_game_prob, market_prob])

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
base = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, random_state=42)
model = CalibratedClassifierCV(base, method="isotonic", cv=3)
model.fit(X_train, y_train)
p = model.predict_proba(X_test)[:, 1]

print("AUC:", roc_auc_score(y_test, p))
print("Brier:", brier_score_loss(y_test, p))
print("LogLoss:", log_loss(y_test, p))

Path("data/models").mkdir(parents=True, exist_ok=True)
joblib.dump(model, "data/models/baseline_winprob.joblib")
print("saved data/models/baseline_winprob.joblib")
