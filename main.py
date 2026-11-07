import streamlit as st


def predict_tomorrow_profit(
        previous_sales: float,
        production_quantity: float,
        cost_per_item: float,
        price_per_item: float,
        leftover_inventory: float = 0.0
):
    """Simple profit-based demand prediction for food vendor."""

    # 1. Estimate demand (similar to previous period)
    predicted_demand = previous_sales

    # 2. Adjust for leftover inventory
    usable_inventory = min(predicted_demand, leftover_inventory)
    new_production_needed = max(0, predicted_demand - leftover_inventory)

    # 3. Calculate revenue
    revenue = predicted_demand * price_per_item

    # 4. Calculate COGS
    cogs = (new_production_needed * cost_per_item) + (usable_inventory * cost_per_item)

    # 5. Calculate profit
    profit = revenue - cogs

    # 6. Estimate waste
    total_production = new_production_needed + leftover_inventory
    estimated_waste = max(0, total_production - predicted_demand)
    waste_cost = estimated_waste * cost_per_item

    # 7. Calculate savings
    savings_from_inventory = usable_inventory * cost_per_item
    savings_from_efficiency = (total_production - predicted_demand) * cost_per_item * 0.3
    total_savings = savings_from_inventory + max(0, savings_from_efficiency)

    # 8. Calculate less waste
    previous_waste_estimate = max(1, production_quantity - previous_sales)
    less_waste = max(0, (previous_waste_estimate - estimated_waste) / previous_waste_estimate)

    return {
        'Profit for Tomorrow': round(profit, 2),
        'Savings': round(total_savings, 2),
        'Less Waste': round(less_waste, 2),
        'Predicted Demand': round(predicted_demand, 1),
        'Production Needed': round(new_production_needed, 1),
        'Usable Inventory': round(usable_inventory, 1)
    }


# === STREAMLIT UI ===

st.title("🍳 Food Vendor Profit Predictor")
st.header("📊 Tomorrow's Profit Calculator")

# Input section
st.header("📋 Input Data")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    previous_sales = st.number_input("Previous Sales (items sold)", min_value=0, value=100, step=10)

with col2:
    production_quantity = st.number_input("Production Quantity (items made)", min_value=0, value=120, step=10)

with col3:
    cost_per_item = st.number_input("Cost per Item ($)", min_value=0.0, value=5.0, step=0.5)

with col4:
    price_per_item = st.number_input("Price per Item ($)", min_value=0.0, value=10.0, step=0.5)

with col5:
    leftover_inventory = st.number_input(
        "Leftover Inventory (items)",
        min_value=0.0,  # float
        value=0.0,  # float
        step=10.0  # float ← FIXED!
    )

# Prediction button
if st.button("🔮 Predict Tomorrow's Profit"):
    results = predict_tomorrow_profit(
        previous_sales=previous_sales,
        production_quantity=production_quantity,
        cost_per_item=cost_per_item,
        price_per_item=price_per_item,
        leftover_inventory=leftover_inventory
    )

    # Output section
    st.header("✅ Predictions")

    st.metric("📈 Profit for Tomorrow", f"${results['Profit for Tomorrow']:.2f}")
    st.metric("💰 Savings", f"${results['Savings']:.2f}")
    st.metric("♻️ Less Waste", f"{results['Less Waste']:.2f}x")

    # Additional details
    st.subheader("📊 Additional Info")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.info(f"🎯 **Predicted Demand**: {results['Predicted Demand']} items")

    with col2:
        st.info(f"🏭 **Production Needed**: {results['Production Needed']} items")

    with col3:
        st.info(f"📦 **Usable Inventory**: {results['Usable Inventory']} items")