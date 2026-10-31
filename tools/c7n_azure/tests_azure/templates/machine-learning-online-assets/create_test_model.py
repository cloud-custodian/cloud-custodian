#!/usr/bin/env python3
"""Create and validate the model artifact for Azure ML online deployment tests."""

import pickle
from pathlib import Path

import click


def create_model():
    try:
        import numpy as np
        from sklearn.linear_model import LinearRegression
    except ImportError as error:
        raise SystemExit(
            "Creating the Azure ML test model requires numpy and scikit-learn. "
            "Install them in the recording environment before provisioning."
        ) from error

    model = LinearRegression()
    model.fit(np.array([[1.0], [2.0], [3.0]]), np.array([1.0, 2.0, 3.0]))
    return model, np


@click.command()
@click.option('--output-dir', required=True, type=click.Path(path_type=Path, file_okay=False))
def main(output_dir):
    model, np = create_model()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / 'model.pkl'
    with model_path.open('wb') as model_file:
        pickle.dump(model, model_file, protocol=4)

    with model_path.open('rb') as model_file:
        loaded_model = pickle.load(model_file)
    prediction = loaded_model.predict(np.array([[4.0]]))
    if not np.isclose(prediction[0], 4.0):
        raise RuntimeError('The generated test model returned an unexpected prediction.')

    import sklearn
    print(sklearn.__version__)


if __name__ == '__main__':
    main()
