import numpy as np
from sklearn.base import BaseEstimator
from sklearn.preprocessing import LabelBinarizer
from sklearn.preprocessing import LabelEncoder
from hiclass._calibration.VennAbersCalibrator import _InductiveVennAbersCalibrator, _CrossVennAbersCalibrator
from hiclass._calibration.IsotonicRegression import _IsotonicRegression
from hiclass._calibration.PlattScaling import _PlattScaling


class _Calibrator(BaseEstimator):
    available_methods = ["ivap", "cvap", "sigmoid", "isotonic"]

    def __init__(self, estimator, method="ivap", **method_params) -> None:
        assert callable(getattr(estimator, 'predict_proba', None))
        self.estimator = estimator
        self.method_params = method_params
        self.classes_ = self.estimator.classes_
        self.multiclass = False
        if method not in self.available_methods:
            raise ValueError(f"{method} is not a valid calibration method.")
        self.method = method

    def fit(self, X, y):
        """
        Fit a calibrator.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            The calibration input samples. Internally, its dtype will be converted
            to ``dtype=np.float32``. If a sparse matrix is provided, it will be
            converted into a sparse ``csc_matrix``.
        y : array-like of shape (n_samples, n_levels)
            The target values, i.e., hierarchical class labels for classification.

        Returns
        -------
        self : object
            Calibrated estimator.
        """
        calibration_scores = self.estimator.predict_proba(X)

        if calibration_scores.shape[1] > 2:
            self.multiclass = True

        self.calibrators = []

        if self.multiclass:
            # binarize multiclass labels
            label_binarizer = LabelBinarizer(sparse_output=False)
            binary_labels = label_binarizer.fit_transform(y).T

            # split scores into k one vs rest splits
            score_splits = [calibration_scores[:, i] for i in range(calibration_scores.shape[1])]

            for idx, split in enumerate(score_splits):
                # create a calibrator for each step
                calibrator = self._create_calibrator(self.method, self.method_params)
                calibrator.fit(binary_labels[idx], split, X)
                self.calibrators.append(calibrator)

        else:
            self.label_encoder = LabelEncoder()
            encoded_y = self.label_encoder.fit_transform(y)
            print(f"after encoding: {np.unique(encoded_y)}")
            calibrator = self._create_calibrator(self.method, self.method_params)
            calibrator.fit(encoded_y, calibration_scores[:, 1], X)
            self.calibrators.append(calibrator)
        return self

    def predict_proba(self, X):
        test_scores = self.estimator.predict_proba(X)

        if self.multiclass:
            score_splits = [test_scores[:, i] for i in range(test_scores.shape[1])]

            probabilities = np.zeros((X.shape[0], len(self.estimator.classes_)))
            for idx, split in enumerate(score_splits):
                probabilities[:, idx] = self.calibrators[idx].predict_proba(split)

            probabilities /= probabilities.sum(axis=1, keepdims=True)

        else:
            probabilities = np.zeros((X.shape[0], 2))
            probabilities[:, 1] = self.calibrators[0].predict_proba(test_scores[:, 1])
            probabilities[:, 0] = 1.0 - probabilities[:, 1]

        return probabilities

    def _create_calibrator(self, name, params):
        if name == "ivap":
            return _InductiveVennAbersCalibrator(**params)
        elif name == "cvap":
            return _CrossVennAbersCalibrator(self.estimator, **params)
        elif name == "sigmoid":
            return _PlattScaling()
        elif name == "isotonic":
            return _IsotonicRegression(params)
