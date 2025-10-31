import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import pytz
import json

# API configuration
API_BASE_URL = "http://localhost:8000/api"

# Page configuration
st.set_page_config(
    page_title="Trading Analytics Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .stSelectbox, .stTextInput, .stNumberInput, .stDateInput {
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075);
    }
    .alert-card {
        border-left: 4px solid #ff4b4b;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        background-color: #fff8f8;
        border-radius: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'symbols' not in st.session_state:
    st.session_state.symbols = []
if 'selected_symbols' not in st.session_state:
    st.session_state.selected_symbols = []
if 'timeframe' not in st.session_state:
    st.session_state.timeframe = '1m'
if 'analytics_data' not in st.session_state:
    st.session_state.analytics_data = {}

# Utility functions
def fetch_symbols():
    """Fetch available symbols from the API"""
    try:
        print(f"Fetching symbols from: {API_BASE_URL}/symbols")  # Debug log
        response = requests.get(f"{API_BASE_URL}/symbols")
        print(f"Response status: {response.status_code}")  # Debug log
        print(f"Response content: {response.text}")  # Debug log
        response.raise_for_status()
        st.session_state.symbols = response.json()
        print(f"Symbols fetched: {st.session_state.symbols}")  # Debug log
        if not st.session_state.selected_symbols and st.session_state.symbols:
            st.session_state.selected_symbols = st.session_state.symbols[:2]
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching symbols: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        st.session_state.symbols = []
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        st.session_state.symbols = []

def fetch_ohlcv(symbol: str, interval: str, limit: int = 1000) -> pd.DataFrame:
    """Fetch OHLCV data for a symbol"""
    try:
        end_time = datetime.now(pytz.utc)
        start_time = end_time - timedelta(hours=24)  # Default to 24 hours
        
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        url = f"{API_BASE_URL}/ohlcv/{symbol}"
        print(f"Fetching OHLCV from: {url} with params: {params}")  # Debug log
        
        response = requests.get(url, params=params)
        print(f"OHLCV Response status: {response.status_code}")  # Debug log
        print(f"OHLCV Response content: {response.text[:200]}...")  # Debug log (first 200 chars)
        
        response.raise_for_status()
        data = response.json()
        
        if not data:
            print("No data returned from API")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        print(f"OHLCV DataFrame shape: {df.shape}")  # Debug log
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            print(f"OHLCV data sample:\n{df.head()}")  # Debug log
            
        return df
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error fetching OHLCV data: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        return pd.DataFrame()
    except Exception as e:
        error_msg = f"Unexpected error processing OHLCV data: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        return pd.DataFrame()

def fetch_analytics(symbol1: str, symbol2: str = None) -> dict:
    """Fetch analytics data for a symbol or symbol pair"""
    try:
        params = {
            'symbol1': symbol1,
            'interval': st.session_state.timeframe
        }
        
        if symbol2:
            params['symbol2'] = symbol2
        
        url = f"{API_BASE_URL}/analytics"
        print(f"Fetching analytics from: {url} with params: {params}")  # Debug log
            
        response = requests.get(url, params=params)
        print(f"Analytics Response status: {response.status_code}")  # Debug log
        print(f"Analytics Response content: {response.text[:500]}...")  # Debug log (first 500 chars)
        
        response.raise_for_status()
        data = response.json()
        print(f"Analytics data received: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        return data
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error fetching analytics: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        return {}
    except Exception as e:
        error_msg = f"Unexpected error processing analytics: {str(e)}"
        print(error_msg)  # Debug log
        st.error(error_msg)
        return {}

def create_candlestick_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """Create a candlestick chart with volume"""
    fig = make_subplots(
        rows=2, 
        cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3]
    )
    
    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price',
            increasing_line_color='#2ecc71',
            decreasing_line_color='#e74c3c'
        ),
        row=1, col=1
    )
    
    # Volume bars
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df['volume'],
            name='Volume',
            marker_color='#3498db',
            opacity=0.7
        ),
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        title=f"{symbol} Price & Volume",
        xaxis_title="Date",
        yaxis_title="Price",
        yaxis2_title="Volume",
        showlegend=False,
        height=600,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white"
    )
    
    # Update x-axes
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)
    
    return fig

def create_analytics_chart(data: dict, title: str) -> go.Figure:
    """Create a line chart for analytics data"""
    fig = go.Figure()
    
    for metric, values in data.items():
        if not values:
            continue
            
        df = pd.DataFrame(values)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['value'],
                name=metric.replace('_', ' ').title(),
                mode='lines'
            )
        )
    
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Value",
        showlegend=True,
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white"
    )
    
    return fig

# Sidebar
with st.sidebar:
    st.title("Trading Analytics")
    
    # Symbol selection
    st.subheader("Symbols")
    
    # Refresh symbols button
    if st.button("🔄 Refresh Symbols"):
        fetch_symbols()
    
    # Symbol multi-select
    if st.session_state.symbols:
        selected = st.multiselect(
            "Select Symbols",
            options=st.session_state.symbols,
            default=st.session_state.selected_symbols,
            key="symbol_selector"
        )
        st.session_state.selected_symbols = selected
    else:
        st.warning("No symbols available. Click 'Refresh Symbols' to load symbols.")
    
    # Timeframe selection
    st.subheader("Timeframe")
    timeframe = st.selectbox(
        "Select Timeframe",
        options=["1m", "5m", "15m", "1h", "4h", "1d"],
        index=2,  # Default to 15m
        key="timeframe_selector"
    )
    
    # Analytics settings
    st.subheader("Analytics")
    show_analytics = st.checkbox("Show Analytics", value=True)
    
    # Alerts
    st.subheader("Alerts")
    if st.button("Create New Alert"):
        st.session_state.show_alert_modal = True
    
    # Display active alerts
    try:
        response = requests.get(f"{API_BASE_URL}/alerts", params={"active_only": True})
        if response.status_code == 200:
            alerts = response.json()
            if alerts:
                st.subheader("Active Alerts")
                for alert in alerts:
                    with st.container():
                        st.markdown(f"""
                        <div class="alert-card">
                            <strong>{alert['name']}</strong><br>
                            {alert['symbol']} - {alert['condition']}<br>
                            <small>Created: {alert['created_at'].split('T')[0]}</small>
                        </div>
                        """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error fetching alerts: {e}")

# Main content
st.title("Trading Analytics Dashboard")

# Fetch data if symbols are selected
if st.session_state.selected_symbols:
    # Create tabs for each selected symbol
    tabs = st.tabs([f"{symbol.upper()}" for symbol in st.session_state.selected_symbols])
    
    for idx, symbol in enumerate(st.session_state.selected_symbols):
        with tabs[idx]:
            # Fetch OHLCV data
            df = fetch_ohlcv(symbol, st.session_state.timeframe)
            
            if not df.empty:
                # Display metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Current Price", f"${df['close'].iloc[-1]:.2f}")
                with col2:
                    price_change = ((df['close'].iloc[-1] - df['open'].iloc[0]) / df['open'].iloc[0]) * 100
                    st.metric("24h Change", f"{price_change:.2f}%")
                with col3:
                    st.metric("24h High", f"${df['high'].max():.2f}")
                with col4:
                    st.metric("24h Volume", f"{df['volume'].sum():.2f}")
                
                # Display price chart
                st.plotly_chart(
                    create_candlestick_chart(df, symbol),
                    use_container_width=True
                )
                
                # Display analytics if enabled
                if show_analytics:
                    st.subheader("Analytics")
                    
                    # Fetch analytics data
                    analytics_data = fetch_analytics(symbol)
                    
                    if analytics_data:
                        # Display each metric in its own chart
                        for metric, values in analytics_data.items():
                            if values:  # Only display if we have data
                                st.plotly_chart(
                                    create_analytics_chart(
                                        {metric: values},
                                        f"{metric.replace('_', ' ').title()} - {symbol.upper()}"
                                    ),
                                    use_container_width=True
                                )
                    else:
                        st.info("No analytics data available. The system may need more data to generate analytics.")
            else:
                st.warning(f"No data available for {symbol}. Please check the symbol and try again.")
    
    # Pair analytics if exactly two symbols are selected
    if len(st.session_state.selected_symbols) == 2:
        st.subheader("Pair Analytics")
        
        symbol1, symbol2 = st.session_state.selected_symbols
        pair_data = fetch_analytics(symbol1, symbol2)
        
        if pair_data:
            for metric, values in pair_data.items():
                if values:  # Only display if we have data
                    st.plotly_chart(
                        create_analytics_chart(
                            {metric: values},
                            f"{metric.replace('_', ' ').title()} - {symbol1.upper()}/{symbol2.upper()}"
                        ),
                        use_container_width=True
                    )
        else:
            st.info("No pair analytics available. The system may need more data to generate pair analytics.")
else:
    st.info("Please select at least one symbol from the sidebar to view data.")

# Alert creation modal
if st.session_state.get('show_alert_modal', False):
    with st.form("alert_form"):
        st.subheader("Create New Alert")
        
        alert_name = st.text_input("Alert Name", "Price Alert")
        alert_symbol = st.selectbox("Symbol", st.session_state.symbols)
        alert_condition = st.selectbox(
            "Condition",
            ["Price > X", "Price < X", "24h Change > X%", "24h Change < X%"]
        )
        alert_value = st.number_input("Value", value=0.0, step=0.01)
        
        submitted = st.form_submit_button("Create Alert")
        cancel = st.form_submit_button("Cancel")
        
        if submitted:
            try:
                # Format the condition for the API
                condition_map = {
                    "Price > X": f"price > {alert_value}",
                    "Price < X": f"price < {alert_value}",
                    "24h Change > X%": f"change_24h > {alert_value}",
                    "24h Change < X%": f"change_24h < {alert_value}",
                }
                
                response = requests.post(
                    f"{API_BASE_URL}/alerts",
                    json={
                        "name": alert_name,
                        "symbol": alert_symbol.upper(),
                        "condition": condition_map[alert_condition],
                        "is_active": True
                    }
                )
                
                if response.status_code == 201:
                    st.success("Alert created successfully!")
                    st.session_state.show_alert_modal = False
                    st.rerun()
                else:
                    st.error(f"Error creating alert: {response.text}")
            except Exception as e:
                st.error(f"Error creating alert: {e}")
        
        if cancel:
            st.session_state.show_alert_modal = False
            st.rerun()

# Initial data fetch
if not st.session_state.symbols:
    fetch_symbols()

# Auto-refresh every 60 seconds
st_autorefresh(interval=60 * 1000, key="auto_refresh")
