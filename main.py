import json
from pathlib import Path

import pandas as pd
import streamlit as st

import predict
from entry import Entry

HISTORY_FILE = Path(__file__).parent / "history.json"

SAMPLE_HISTORY = [
    Entry(sold=43, produced=50, cost=1.50, price=4.00),
    Entry(sold=40, produced=40, cost=1.50, price=4.00),
    Entry(sold=45, produced=55, cost=1.50, price=4.00),
    Entry(sold=39, produced=45, cost=1.50, price=4.00),
    Entry(sold=50, produced=50, cost=1.50, price=4.00),
]


def load_history() -> list[Entry]:
    if not HISTORY_FILE.exists():
        return []
    with HISTORY_FILE.open() as f:
        return [Entry.from_dict(d) for d in json.load(f)]


def save_history(history: list[Entry]) -> None:
    with HISTORY_FILE.open("w") as f:
        json.dump([e.to_dict() for e in history], f, indent=2)


if "history" not in st.session_state:
    st.session_state.history = load_history()

history: list[Entry] = st.session_state.history

st.title("Waste Minimizer")

# ---------- Add today's entry ----------
st.subheader("Add today's numbers")

last = history[-1] if history else None
with st.form("new_entry", clear_on_submit=True):
    col1, col2 = st.columns(2)
    produced = col1.number_input("Units produced", min_value=1, step=1, value=last.produced if last else 50)
    sold = col2.number_input("Units sold", min_value=0, step=1, value=0)
    cost = col1.number_input("Cost to make (per unit)", min_value=0.0, step=0.05, format="%.2f",
                             value=last.cost if last else 1.00)
    price = col2.number_input("Selling price (per unit)", min_value=0.0, step=0.05, format="%.2f",
                              value=last.price if last else 3.00)
    submitted = st.form_submit_button("Add entry")

if submitted:
    try:
        history.append(Entry(sold=int(sold), produced=int(produced), cost=cost, price=price))
        save_history(history)
        st.rerun()
    except ValueError as e:
        st.error(str(e))

# ---------- Prediction ----------
st.subheader("Tomorrow")

if not history:
    st.info("Add your first day's numbers to get a prediction.")
    if st.button("Load sample data"):
        history.extend(SAMPLE_HISTORY)
        save_history(history)
        st.rerun()
else:
    result = predict.predict_demand(history)
    lo, hi = result["prediction_interval_80"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Expected demand", result["predicted_demand"])
    c2.metric("80% range", f"{lo} – {hi}")
    c3.metric("Recommended to make", result["recommended_production"])

    # ---------- History ----------
    st.subheader("History")
    df = pd.DataFrame(
        [{**e.to_dict(), "wasted": e.wasted, "sold_out": e.sold_out, "profit": round(e.profit, 2)}
         for e in history]
    )
    df.index = [f"Day {i + 1}" for i in range(len(df))]
    st.dataframe(df, use_container_width=True)

    if st.button("Undo last entry"):
        history.pop()
        save_history(history)
        st.rerun()
