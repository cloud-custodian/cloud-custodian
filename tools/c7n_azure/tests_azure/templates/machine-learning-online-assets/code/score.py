import os
import pickle
from pathlib import Path

import numpy as np


model = None


def init():
    global model
    model_directory = Path(os.environ['AZUREML_MODEL_DIR'])
    model_path = next(model_directory.rglob('model.pkl'))
    with model_path.open('rb') as model_file:
        model = pickle.load(model_file)


def run(data):
    return model.predict(np.asarray(data['instances'])).tolist()
