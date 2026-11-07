import streamlit as st
import numpy as np
import pandas as pd
from scipy import stats
import predict

history = [
    {"prepared": 50, "sold": 43},
    {"prepared": 40, "sold": 40},
    {"prepared": 55, "sold": 45},
    {"prepared": 45, "sold": 39},
    {"prepared": 50, "sold": 50}
]

result = predict.predict_demand(history) #Call method


st.write(result)
