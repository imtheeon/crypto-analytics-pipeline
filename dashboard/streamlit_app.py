"""Crypto market dashboard. Reads crypto_metrics views only, as crypto-dashboard-sa.

Run:      streamlit run dashboard/streamlit_app.py   (from the repo root, so .streamlit/config.toml applies)
Secrets:  [gcp_service_account] in .streamlit/secrets.toml, or the app's secrets on Community Cloud.
          Without it, falls back to GOOGLE_APPLICATION_CREDENTIALS.
Cost:     one query per cache fill. Cache lasts 1 hour, shared by all viewers. No auto-refresh.
          "Refresh now" clears it at most once every 5 minutes across all viewers.
"""
import html
import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery
from google.oauth2 import service_account

from crypto_dashboard_logic import (DAY, anomaly_count_24h, available_around, insights, is_stale, latest_per_coin,
                                    movers, total_market_cap, usd)

PROJECT = "crypto-analytics-pipeline-lc"
REFRESH_COOLDOWN_S = 300
MAX_COINS = 5
# Dataviz reference palette and chrome, one set per theme. Series validated on each card surface
# (light: 3 slots under 3:1 contrast, relieved by direct labels, dashes, legend and the anomaly table).
TOKENS = {
    "dark": dict(series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"], surface="#1a1a19",
                 ink2="#c3c2b7", muted="#898781", grid="#2c2c2a"),
    "light": dict(series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"], surface="#fcfcfb",
                  ink2="#52514e", muted="#898781", grid="#e1e0d9"),
}
GOOD, BAD = "#0ca30c", "#d03b3b"  # status colors, same in both themes; always paired with an arrow
DASHES = ["solid", "dash", "dot", "dashdot", "longdash"]
RANGES = {"24H": pd.Timedelta(hours=24), "7D": pd.Timedelta(days=7), "30D": pd.Timedelta(days=30), "All": None}

st.set_page_config(page_title="Crypto Pulse", page_icon=":material/monitoring:", layout="wide")

tok = TOKENS["light" if st.context.theme.type == "light" else "dark"]
SERIES, SURFACE, INK2, MUTED, GRID = tok["series"], tok["surface"], tok["ink2"], tok["muted"], tok["grid"]

st.html(f"""<style>
.block-container {{ padding-top: 2rem; max-width: 1400px; }}
[class*="st-key-card"] {{ background: {SURFACE}; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }}
.kpi {{ background: {SURFACE}; border: 1px solid {GRID}; border-radius: 12px; padding: 16px 18px; }}
.kpi-label {{ color: {INK2}; font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; }}
.kpi-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.7rem; font-weight: 600; margin: 6px 0 4px; }}
.kpi-sub {{ color: {MUTED}; font-size: .85rem; }}
.kpi-value.pending {{ font-family: inherit; font-size: 1.15rem; color: {INK2}; margin: 12px 0 8px; }}
.chip {{ font-family: 'JetBrains Mono', monospace; font-size: .85rem; font-weight: 600; }}
.up {{ color: {GOOD}; }} .down {{ color: {BAD}; }}
.eyebrow {{ color: {MUTED}; font-size: .85rem; }}
.insight {{ margin: 0 0 .4rem; color: {INK2}; }}
</style>""")


# ---------- data ----------

@st.cache_resource
def bq_client():
    try:
        info = dict(st.secrets["gcp_service_account"])
    except (KeyError, FileNotFoundError):
        return bigquery.Client(project=PROJECT)  # local dev: GOOGLE_APPLICATION_CREDENTIALS
    return bigquery.Client(project=PROJECT, credentials=service_account.Credentials.from_service_account_info(info))


@st.cache_data(ttl="1h", show_spinner="Loading prices from BigQuery…")
def load_prices():
    """All rows the sandbox keeps (60 days), plus the anomaly threshold. One query.

    A failed query returns (None, time) instead of raising, so the failure is cached too and viewers
    can't trigger a retry on every click. The 1 GB cap stops a runaway query; the normal scan is a few MB.
    """
    try:
        df = bq_client().query(f"""
        SELECT p.coin_id, p.name, p.observed_at, p.current_price, p.market_cap, p.return_15m, p.pct_change_24h,
               p.ma_7d, p.ma_7d_is_partial, p.volatility_24h, p.z_score, p.is_anomaly, c.z_threshold
        FROM `{PROJECT}.crypto_metrics.prices` AS p
        CROSS JOIN `{PROJECT}.crypto_metrics.anomaly_config` AS c
    """, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=10**9)).to_dataframe(create_bqstorage_client=False)
    except GoogleAPIError:
        return None, datetime.now(timezone.utc)
    return df, datetime.now(timezone.utc)


@st.cache_resource
def refresh_gate():
    """Shared by every session, so the 5-minute limit holds across all viewers."""
    return {"last": 0.0}  # ponytail: no lock; two clicks in the same instant could both clear. Harmless.


# ---------- formatting ----------

def pct(v, places=2):
    return "n/a" if v is None or pd.isna(v) else f"{v * 100:+.{places}f}%"


def chip(v):
    """Arrow carries the color; the number stays in text ink."""
    if v is None or pd.isna(v):
        return '<span class="chip kpi-sub">no 24h data yet</span>'
    arrow, cls = ("▲", "up") if v >= 0 else ("▼", "down")
    return f'<span class="chip"><span class="{cls}">{arrow}</span> {pct(v)}</span>'


def around(ts):
    """'14:30 UTC' today, 'Oct 6, 14:30 UTC' on another day (relative to the newest data)."""
    return f"{ts:%H:%M} UTC" if ts.date() == newest.date() else f"{ts:%b} {ts.day}, {ts:%H:%M} UTC"


def collecting_card(label, ready_at):
    return f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value pending">Collecting data</div>' \
           f'<div class="kpi-sub">Available around {around(ready_at)}</div></div>'


def ago(ts, now):
    minutes = int((now - ts).total_seconds() // 60)
    return f"{minutes} min ago" if minutes < 120 else f"{minutes // 60} h ago"


def style(fig, height=380):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=INK2, size=13), hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRID, font=dict(family="JetBrains Mono, monospace", size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, tickfont_color=MUTED, showspikes=True, spikecolor=MUTED,
                     spikethickness=1, spikedash="dot", spikemode="across")
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, tickfont_color=MUTED, zeroline=False)
    return fig


# ---------- header ----------

df, fetched_at = load_prices()
now = datetime.now(timezone.utc)
if df is None:
    st.error("Couldn't load data from BigQuery. It will retry within the hour.", icon=":material/error:")
    st.stop()
newest = df["observed_at"].max() if not df.empty else pd.NaT

head, actions = st.columns([3, 1], vertical_alignment="bottom")
with head:
    st.markdown('<div class="eyebrow">10 COINS · COINGECKO · LOADED EVERY 15 MIN</div>', unsafe_allow_html=True)
    st.title("Crypto Pulse", anchor=False)
with actions:
    gate = refresh_gate()
    wait = int(REFRESH_COOLDOWN_S - (time.time() - gate["last"]))
    if st.button("Refresh now", icon=":material/refresh:", disabled=wait > 0, width="stretch",
                 help=f"Available again in {wait // 60}m {wait % 60:02d}s" if wait > 0 else
                 "Reload from BigQuery. Limited to once every 5 minutes for all viewers.") and wait <= 0:
        gate["last"] = time.time()
        load_prices.clear()
        st.rerun()
    as_of = "no data" if pd.isna(newest) else f"{newest:%Y-%m-%d %H:%M} UTC ({ago(newest, now)})"
    st.caption(f"Data as of {as_of}  \nLast updated {fetched_at:%H:%M} UTC · cached for 1 hour")

if is_stale(newest, fetched_at):  # judged at fetch time: cached data is up to 1 hour old by design
    st.warning(f"Data is stale. The newest observation was {'missing' if pd.isna(newest) else ago(newest, fetched_at)} "
               "when it was loaded. "
               "The pipeline normally loads every 15 minutes.", icon=":material/schedule:")
if df.empty:
    st.info("No data in crypto_metrics.prices yet. It appears after the first pipeline run.", icon=":material/hourglass_empty:")
    st.stop()


# ---------- KPI cards ----------

total, total_chg = total_market_cap(df)
gainer, loser = movers(df)
flagged, checked = anomaly_count_24h(df)
threshold = df["z_threshold"].iloc[0]
eta = available_around(df)


def mover_card(label, row):
    if row is None:
        return collecting_card(label, eta["change_24h"])
    return f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{html.escape(row["name"])}</div>' \
           f'{chip(row["pct_change_24h"])} <span class="kpi-sub">· {usd(row["current_price"])}</span></div>'


no_change = total_chg is None or pd.isna(total_chg)
total_sub = f'<span class="kpi-sub">24h change available around {around(eta["change_24h"])}</span>' if no_change \
    else f'{chip(total_chg)} <span class="kpi-sub">· 24h</span>'
anomaly_card = collecting_card("Anomalies · 24h", eta["anomaly"]) if not checked else \
    f'<div class="kpi"><div class="kpi-label">Anomalies · 24h</div><div class="kpi-value">{flagged}</div>' \
    f'<div class="kpi-sub">of {checked:,} checks · |z| ≥ {threshold:g}</div></div>'
st.html(f"""<div class="kpis">
  <div class="kpi"><div class="kpi-label">Total market cap</div><div class="kpi-value">{usd(total)}</div>{total_sub}</div>
  {mover_card("Biggest gainer · 24h", gainer)}
  {mover_card("Biggest loser · 24h", loser)}
  {anomaly_card}
</div>""")
if no_change or gainer is None or not checked:
    st.caption("Estimated times assume a pipeline run every 15 minutes.")


# ---------- controls ----------

names = df.drop_duplicates("coin_id").set_index("coin_id")["name"].sort_values()
c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
coins = c1.multiselect("Coins", list(names.index), default=["bitcoin"], format_func=names.get,
                       max_selections=MAX_COINS, placeholder="Pick up to 5 coins")
range_key = c2.segmented_control("Range", list(RANGES), default="7D", width="stretch") or "7D"

# Color follows the coin, not its position: a coin keeps its slot while it stays selected.
slots = {c: s for c, s in st.session_state.get("slots", {}).items() if c in coins}
for c in coins:
    if c not in slots:
        slots[c] = min(set(range(MAX_COINS)) - set(slots.values()))
st.session_state["slots"] = slots

window = df if RANGES[range_key] is None else df[df["observed_at"] > newest - RANGES[range_key]]
window = window.sort_values("observed_at")


# ---------- price chart ----------

with st.container(border=True, key="card-price"):
    if not coins:
        st.subheader("Price", anchor=False)
        st.caption("Pick a coin to see its price.")
    elif len(coins) == 1:
        coin = coins[0]
        d = window[window["coin_id"] == coin]
        st.subheader(f"{names[coin]} price", anchor=False)
        st.caption("USD, with the trailing 7-day average and anomaly flags."
                   + (f" The 7-day average is partial until around {around(eta['ma_7d'])}."
                      if not d.empty and d["ma_7d_is_partial"].fillna(False).iloc[-1] else ""))
        fig = go.Figure()
        fig.add_scatter(x=d["observed_at"], y=d["current_price"], name="Price", mode="lines",
                        line=dict(color=SERIES[slots[coin]], width=2), hovertemplate="%{y:$,.4~f}<extra>Price</extra>")
        fig.add_scatter(x=d["observed_at"], y=d["ma_7d"], name="7-day avg", mode="lines",
                        line=dict(color=MUTED, width=2, dash="dot"), hovertemplate="%{y:$,.4~f}<extra>7-day avg</extra>")
        a = d[d["is_anomaly"] == True]  # noqa: E712
        fig.add_scatter(x=a["observed_at"], y=a["current_price"], name="Anomaly", mode="markers",
                        marker=dict(color=BAD, size=10, line=dict(color=SURFACE, width=2)),
                        customdata=a["z_score"], hovertemplate="z = %{customdata:.1f}<extra>Anomaly</extra>")
        fig.update_yaxes(tickprefix="$", tickformat=",.4~f")
        st.plotly_chart(style(fig), width="stretch", config={"displayModeBar": False})
    else:
        st.subheader("Price change", anchor=False)
        st.caption(f"% change since the start of the {range_key} range, so coins at very different prices compare on one axis.")
        fig = go.Figure()
        for coin in coins:
            d = window[window["coin_id"] == coin].dropna(subset=["current_price"])
            if d.empty:
                continue
            change = d["current_price"] / d["current_price"].iloc[0] - 1
            color = SERIES[slots[coin]]
            fig.add_scatter(x=d["observed_at"], y=change, name=names[coin], mode="lines",
                            line=dict(color=color, width=2, dash=DASHES[slots[coin]]),  # dash: not color alone
                            hovertemplate="%{y:+.2%}<extra>" + names[coin] + "</extra>")
            if len(coins) <= 4:  # direct labels at the line ends; the legend covers 5
                fig.add_annotation(x=d["observed_at"].iloc[-1], y=change.iloc[-1], text=names[coin], showarrow=False,
                                   xanchor="left", xshift=6, font=dict(color=INK2, size=12))
        fig.update_yaxes(tickformat="+.1%")
        fig.update_layout(margin=dict(r=90))
        st.plotly_chart(style(fig), width="stretch", config={"displayModeBar": False})


# ---------- volatility + anomalies ----------

left, right = st.columns(2)
latest = latest_per_coin(df)

with left, st.container(border=True, key="card-vol"):
    st.subheader("Volatility · 24h", anchor=False)
    vol = latest.dropna(subset=["volatility_24h"]).sort_values("volatility_24h")
    if vol.empty:
        recent = df[df["observed_at"] > newest - DAY]
        have = int(recent.groupby("coin_id")["return_15m"].count().max())
        st.caption(f"Collecting data, available around {around(eta['volatility'])}. Volatility needs 48 "
                   f"returns (one per 15 minutes) in 24 hours; the most any coin has so far is {have}.")
    else:
        st.caption("Standard deviation of 15-minute returns over the last 24 hours. Not annualized.")
        fig = go.Figure(go.Bar(x=vol["volatility_24h"], y=vol["name"], orientation="h",
                               marker=dict(color=SERIES[0], cornerradius=4), hovertemplate="%{x:.3%}<extra>%{y}</extra>"))
        fig.update_xaxes(tickformat=".2%")
        fig.update_layout(hovermode="closest", bargap=0.35)
        st.plotly_chart(style(fig, height=360), width="stretch", config={"displayModeBar": False})

with right, st.container(border=True, key="card-anom"):
    st.subheader("Anomalies", anchor=False)
    found = window[window["is_anomaly"] == True].sort_values("observed_at", ascending=False)  # noqa: E712
    if window["is_anomaly"].notna().sum() == 0:
        st.caption(f"Collecting data, available around {around(eta['anomaly'])}. "
                   "Anomaly checks need 1 day of 15-minute returns.")
    elif found.empty:
        st.caption(f"No 15-minute move reached |z| ≥ {threshold:g} in the {range_key} range.")
    else:
        st.caption(f"15-minute moves with |z| ≥ {threshold:g} against the coin's own last 7 days, in the {range_key} range.")
        st.dataframe(
            found.assign(return_15m=found["return_15m"] * 100)[["observed_at", "name", "return_15m", "z_score"]],
            hide_index=True, width="stretch", height=320,
            column_config={
                "observed_at": st.column_config.DatetimeColumn("Time (UTC)", format="MMM D, HH:mm"),
                "name": "Coin",
                "return_15m": st.column_config.NumberColumn("15m move", format="%+.2f%%"),
                "z_score": st.column_config.NumberColumn("z-score", format="%+.1f"),
            })


# ---------- insights ----------

with st.container(border=True, key="card-insights"):
    st.subheader("Insights", anchor=False)
    lines = insights(df)
    if lines:
        st.html("".join(f'<p class="insight">{html.escape(line)}</p>' for line in lines))
    else:
        first = min(eta["change_24h"], eta["volatility"], eta["anomaly"])
        st.caption(f"Collecting data. The first insights appear around {around(first)}.")
    st.caption("Each sentence is filled in from the numbers above. They describe the data and are not advice.")
