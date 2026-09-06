from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import optuna
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .common import SENSOR_COLUMNS, periods_for_duration
from .derived_metrics import add_derived_metrics


optuna.logging.set_verbosity(optuna.logging.WARNING)

DEFAULT_TARGETS = {
    "10分後の気温": ("temperature_c", "10m"),
    "1時間後の湿度": ("humidity_pct", "1h"),
    "3時間後の気圧": ("pressure_hpa", "3h"),
}
LSTM_SEQUENCE_LENGTH = 60
LSTM_TRAIN_LIMIT = 50_000
LSTM_EPOCHS = 4
LSTM_BATCH_SIZE = 512
DEFAULT_OPTUNA_TRIALS = 25
DEFAULT_TUNING_TRAIN_SIZE = 50_000
DEFAULT_VALID_RATIO = 0.2


@dataclass(frozen=True)
class ForecastResult:
    metrics: pl.DataFrame
    predictions: pl.DataFrame
    tuning_results: pl.DataFrame


def _feature_frame(df: pl.DataFrame, freq: str) -> tuple[pl.DataFrame, list[str]]:
    enriched = add_derived_metrics(df)
    feature_columns = [
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "dew_point_c",
        "absolute_humidity_g_m3",
        "discomfort_index",
    ]
    expressions = []
    for lag in ["10m", "30m", "1h", "3h"]:
        periods = periods_for_duration(lag, freq)
        for column in SENSOR_COLUMNS:
            lag_column = f"{column}_lag_{lag}"
            expressions.append(pl.col(column).shift(periods).alias(lag_column))
            feature_columns.append(lag_column)

    features = enriched.with_columns(
        [
            *expressions,
            pl.col("timestamp").dt.hour().alias("hour"),
            pl.col("timestamp").dt.weekday().alias("dayofweek"),
        ]
    )
    feature_columns.extend(["hour", "dayofweek"])
    return features.select(["timestamp", *feature_columns]), feature_columns


def _target_expressions(
    targets: dict[str, tuple[str, str]],
    freq: str,
) -> tuple[list[pl.Expr], list[str]]:
    expressions = []
    target_columns = []
    for label, (column, horizon) in targets.items():
        periods = periods_for_duration(horizon, freq)
        expressions.append(pl.col(column).shift(-periods).alias(label))
        target_columns.append(label)
    return expressions, target_columns


def _build_sequences(
    x: np.ndarray,
    y: np.ndarray,
    sequence_length: int,
) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < sequence_length:
        return (
            np.empty((0, sequence_length, x.shape[1]), dtype=np.float32),
            np.empty((0, y.shape[1]), dtype=np.float32),
        )
    sequences = np.stack(
        [x[index - sequence_length + 1 : index + 1] for index in range(sequence_length - 1, len(x))]
    )
    targets = y[sequence_length - 1 :]
    return sequences.astype(np.float32), targets.astype(np.float32)


def _fit_predict_lstm(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    params: dict[str, Any],
    train_limit: int = LSTM_TRAIN_LIMIT,
) -> tuple[np.ndarray, int]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    sequence_length = int(params.get("sequence_length", LSTM_SEQUENCE_LENGTH))
    hidden_size = int(params.get("hidden_size", 32))
    num_layers = int(params.get("num_layers", 1))
    dropout = float(params.get("dropout", 0.0)) if num_layers > 1 else 0.0
    learning_rate = float(params.get("learning_rate", 0.001))
    epochs = int(params.get("epochs", LSTM_EPOCHS))
    batch_size = int(params.get("batch_size", LSTM_BATCH_SIZE))

    class LstmRegressor(nn.Module):
        def __init__(self, input_size: int, output_size: int) -> None:
            super().__init__()
            self.lstm = nn.LSTM(
                input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout,
                batch_first=True,
            )
            self.linear = nn.Linear(hidden_size, output_size)

        def forward(self, values: torch.Tensor) -> torch.Tensor:
            output, _ = self.lstm(values)
            return self.linear(output[:, -1, :])

    x_scaler = StandardScaler()
    y_scaler = StandardScaler()
    x_train_scaled = x_scaler.fit_transform(x_train)
    y_train_scaled = y_scaler.fit_transform(y_train)
    x_test_scaled = x_scaler.transform(x_test)

    train_sequences, train_targets = _build_sequences(
        x_train_scaled,
        y_train_scaled,
        sequence_length,
    )
    if len(train_sequences) > train_limit:
        train_sequences = train_sequences[-train_limit:]
        train_targets = train_targets[-train_limit:]

    x_context = np.vstack([x_train_scaled[-(sequence_length - 1) :], x_test_scaled])
    y_placeholder = np.zeros((len(x_context), y_train.shape[1]), dtype=np.float32)
    test_sequences, _ = _build_sequences(x_context, y_placeholder, sequence_length)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LstmRegressor(x_train.shape[1], y_train.shape[1]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = nn.MSELoss()

    dataset = TensorDataset(torch.from_numpy(train_sequences), torch.from_numpy(train_targets))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    model.train()
    for _ in range(epochs):
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()

    model.eval()
    predictions = []
    with torch.no_grad():
        for start in range(0, len(test_sequences), batch_size):
            batch = torch.from_numpy(test_sequences[start : start + batch_size]).to(device)
            predictions.append(model(batch).cpu().numpy())

    predicted_scaled = np.vstack(predictions)
    predicted = y_scaler.inverse_transform(predicted_scaled)
    return predicted, len(train_sequences)


def _target_scaled_rmse(y_true: np.ndarray, y_pred: np.ndarray, scale: np.ndarray) -> float:
    safe_scale = np.where(scale == 0.0, 1.0, scale)
    errors = (y_true - y_pred) / safe_scale
    return float(np.sqrt(np.mean(errors**2)))


def _sample_tail(x: np.ndarray, y: np.ndarray, max_rows: int) -> tuple[np.ndarray, np.ndarray]:
    if len(x) <= max_rows:
        return x, y
    return x[-max_rows:], y[-max_rows:]


def _split_train_validation(
    x: np.ndarray,
    y: np.ndarray,
    valid_ratio: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    valid_size = max(1, min(len(x) - 1, int(len(x) * valid_ratio)))
    train_end = len(x) - valid_size
    return x[:train_end], y[:train_end], x[train_end:], y[train_end:]


def _make_model(model_name: str, params: dict[str, Any]):
    if model_name == "Ridge回帰":
        return make_pipeline(StandardScaler(), Ridge(alpha=float(params["alpha"])))
    if model_name == "Random Forest":
        return RandomForestRegressor(
            n_estimators=int(params["n_estimators"]),
            max_depth=params["max_depth"],
            min_samples_leaf=int(params["min_samples_leaf"]),
            max_features=float(params["max_features"]),
            random_state=42,
            n_jobs=-1,
        )
    if model_name == "勾配ブースティング":
        return MultiOutputRegressor(
            HistGradientBoostingRegressor(
                learning_rate=float(params["learning_rate"]),
                max_iter=int(params["max_iter"]),
                max_leaf_nodes=int(params["max_leaf_nodes"]),
                min_samples_leaf=int(params["min_samples_leaf"]),
                l2_regularization=float(params["l2_regularization"]),
                random_state=42,
            )
        )
    if model_name == "LightGBM":
        from lightgbm import LGBMRegressor

        return MultiOutputRegressor(
            LGBMRegressor(
                n_estimators=int(params["n_estimators"]),
                learning_rate=float(params["learning_rate"]),
                num_leaves=int(params["num_leaves"]),
                max_depth=int(params["max_depth"]),
                min_child_samples=int(params["min_child_samples"]),
                subsample=float(params["subsample"]),
                colsample_bytree=float(params["colsample_bytree"]),
                reg_lambda=float(params["reg_lambda"]),
                random_state=42,
                verbosity=-1,
            )
        )
    raise ValueError(f"未対応のモデルです: {model_name}")


def _suggest_params(trial: optuna.Trial, model_name: str) -> dict[str, Any]:
    if model_name == "Ridge回帰":
        return {"alpha": trial.suggest_float("alpha", 1e-4, 100.0, log=True)}
    if model_name == "Random Forest":
        depth = trial.suggest_int("max_depth", 4, 28)
        return {
            "n_estimators": trial.suggest_int("n_estimators", 120, 500),
            "max_depth": depth,
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
            "max_features": trial.suggest_float("max_features", 0.4, 1.0),
        }
    if model_name == "勾配ブースティング":
        return {
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "max_iter": trial.suggest_int("max_iter", 80, 500),
            "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 8, 64),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 80),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-4, 10.0, log=True),
        }
    if model_name == "LightGBM":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 700),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 8, 96),
            "max_depth": trial.suggest_int("max_depth", 3, 16),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 20.0, log=True),
        }
    if model_name == "LSTM":
        return {
            "sequence_length": trial.suggest_categorical("sequence_length", [30, 60, 120]),
            "hidden_size": trial.suggest_categorical("hidden_size", [16, 32, 64, 96]),
            "num_layers": trial.suggest_int("num_layers", 1, 2),
            "dropout": trial.suggest_float("dropout", 0.0, 0.3),
            "learning_rate": trial.suggest_float("learning_rate", 1e-4, 5e-3, log=True),
            "epochs": trial.suggest_int("epochs", 4, 12),
            "batch_size": trial.suggest_categorical("batch_size", [256, 512, 1024]),
        }
    raise ValueError(f"未対応のモデルです: {model_name}")


def _tune_sklearn_model(
    model_name: str,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    y_scale: np.ndarray,
    n_trials: int,
) -> tuple[dict[str, Any], float]:
    def objective(trial: optuna.Trial) -> float:
        params = _suggest_params(trial, model_name)
        model = _make_model(model_name, params)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names.*",
                category=UserWarning,
            )
            model.fit(x_train, y_train)
            predicted = np.asarray(model.predict(x_valid))
        return _target_scaled_rmse(y_valid, predicted, y_scale)

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return dict(study.best_params), float(study.best_value)


def _tune_lstm_model(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    y_scale: np.ndarray,
    n_trials: int,
    train_limit: int,
) -> tuple[dict[str, Any], float]:
    def objective(trial: optuna.Trial) -> float:
        params = _suggest_params(trial, "LSTM")
        predicted, _ = _fit_predict_lstm(
            x_train,
            y_train,
            x_valid,
            params=params,
            train_limit=train_limit,
        )
        return _target_scaled_rmse(y_valid, predicted, y_scale)

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return dict(study.best_params), float(study.best_value)


def compare_forecasts(
    df: pl.DataFrame,
    freq: str,
    targets: dict[str, tuple[str, str]] | None = None,
    test_ratio: float = 0.2,
    valid_ratio: float = DEFAULT_VALID_RATIO,
    optuna_trials: int = DEFAULT_OPTUNA_TRIALS,
    tuning_train_size: int = DEFAULT_TUNING_TRAIN_SIZE,
    lstm_train_limit: int = LSTM_TRAIN_LIMIT,
) -> ForecastResult:
    if targets is None:
        targets = DEFAULT_TARGETS

    feature_df, feature_columns = _feature_frame(df, freq)
    target_exprs, target_columns = _target_expressions(targets, freq)
    target_df = df.select(["timestamp", *target_exprs])
    dataset = feature_df.join(target_df, on="timestamp").drop_nulls()
    if dataset.height < 20:
        raise ValueError("予測には少なくとも 20 件以上の有効データが必要です。")

    test_split_index = max(1, min(dataset.height - 1, int(dataset.height * (1.0 - test_ratio))))
    train_valid = dataset.slice(0, test_split_index)
    test = dataset.slice(test_split_index)

    x_train_valid = train_valid.select(feature_columns).to_numpy()
    y_train_valid = train_valid.select(target_columns).to_numpy()
    x_test = test.select(feature_columns).to_numpy()
    y_test = test.select(target_columns).to_numpy()

    x_train, y_train, x_valid, y_valid = _split_train_validation(
        x_train_valid,
        y_train_valid,
        valid_ratio,
    )
    x_tune_train, y_tune_train = _sample_tail(x_train, y_train, tuning_train_size)
    y_scale = np.std(y_tune_train, axis=0)

    metric_rows = []
    tuning_rows = []
    prediction_columns: dict[str, list[float]] = {
        "timestamp": test.get_column("timestamp").to_list()
    }
    for index, target in enumerate(target_columns):
        prediction_columns[f"実測_{target}"] = y_test[:, index].tolist()

    model_names = ["Ridge回帰", "Random Forest", "勾配ブースティング", "LightGBM"]
    best_params: dict[str, dict[str, Any]] = {}
    for model_name in model_names:
        params, best_score = _tune_sklearn_model(
            model_name,
            x_tune_train,
            y_tune_train,
            x_valid,
            y_valid,
            y_scale,
            optuna_trials,
        )
        best_params[model_name] = params
        tuning_rows.append(
            {
                "モデル": model_name,
                "validation_scaled_RMSE": best_score,
                "trials": optuna_trials,
                "best_params": str(params),
            }
        )

    lstm_params, lstm_best_score = _tune_lstm_model(
        x_tune_train,
        y_tune_train,
        x_valid,
        y_valid,
        y_scale,
        optuna_trials,
        lstm_train_limit,
    )
    tuning_rows.append(
        {
            "モデル": "LSTM",
            "validation_scaled_RMSE": lstm_best_score,
            "trials": optuna_trials,
            "best_params": str(lstm_params),
        }
    )

    for model_name in model_names:
        model = _make_model(model_name, best_params[model_name])
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names.*",
                category=UserWarning,
            )
            model.fit(x_train_valid, y_train_valid)
            predicted = np.asarray(model.predict(x_test))
        for index, target in enumerate(target_columns):
            actual = y_test[:, index]
            pred = predicted[:, index]
            rmse = float(np.sqrt(mean_squared_error(actual, pred)))
            metric_rows.append(
                {
                    "モデル": model_name,
                    "予測対象": target,
                    "MAE": float(mean_absolute_error(actual, pred)),
                    "RMSE": rmse,
                    "R2": float(r2_score(actual, pred)) if len(actual) >= 2 else None,
                    "学習件数": len(x_train_valid),
                    "評価件数": len(x_test),
                }
            )
            prediction_columns[f"{model_name}_予測_{target}"] = pred.tolist()

    lstm_predicted, lstm_train_count = _fit_predict_lstm(
        x_train_valid,
        y_train_valid,
        x_test,
        params=lstm_params,
        train_limit=lstm_train_limit,
    )
    for index, target in enumerate(target_columns):
        actual = y_test[:, index]
        pred = lstm_predicted[:, index]
        rmse = float(np.sqrt(mean_squared_error(actual, pred)))
        metric_rows.append(
            {
                "モデル": "LSTM",
                "予測対象": target,
                "MAE": float(mean_absolute_error(actual, pred)),
                "RMSE": rmse,
                "R2": float(r2_score(actual, pred)) if len(actual) >= 2 else None,
                "学習件数": lstm_train_count,
                "評価件数": len(x_test),
            }
        )
        prediction_columns[f"LSTM_予測_{target}"] = pred.tolist()

    return ForecastResult(
        metrics=pl.DataFrame(metric_rows),
        predictions=pl.DataFrame(prediction_columns),
        tuning_results=pl.DataFrame(tuning_rows),
    )
