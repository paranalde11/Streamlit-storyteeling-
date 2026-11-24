"""Mexico's electrified vehicle transition — INEGI data journalism dashboard.
Run: python -m streamlit run app.py
"""
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Mexico's Electrified Vehicle Story", page_icon="🚘", layout="wide")
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TECH = {"VEH_HIBRIDAS": "Hybrid (HEV)", "VEH_HIBRIDAS_PLUGIN": "Plug-in hybrid (PHEV)", "VEH_ELECTR": "Fully electric (BEV)"}
ORDER = list(TECH.values())
COLORS = {"Hybrid (HEV)": "#2563A6", "Plug-in hybrid (PHEV)": "#E08B31", "Fully electric (BEV)": "#17856B"}

st.markdown("""<style>
.block-container {max-width: 1200px; padding-top: 1.5rem; padding-bottom: 3rem}
h1,h2,h3 {letter-spacing:-.025em}
.kicker {font-size:.78rem; font-weight:750; letter-spacing:.12em; color:#2563A6}
.deck {font-size:1.12rem; line-height:1.65; max-width:900px}
.insight {border-left:4px solid #17856B; padding:.8rem 1rem; margin:1rem 0; background:rgba(23,133,107,.06)}
</style>""", unsafe_allow_html=True)

@st.cache_data(show_spinner="Loading INEGI data…")
def load_data():
    paths = sorted(DATA.glob("raiavl_hibrido_mensual_tr_cifra_20*.csv"))
    if not paths:
        raise FileNotFoundError("No annual INEGI CSVs found in data/.")
    df = pd.concat([pd.read_csv(p, dtype={"ID_MES":str,"ID_ENTIDAD":str}, encoding="utf-8-sig") for p in paths], ignore_index=True)
    states = pd.read_csv(DATA / "tc_entidad_federativa.csv", dtype={"ID_ENTIDAD":str}, encoding="utf-8-sig")
    months = pd.read_csv(DATA / "tc_mes.csv", dtype={"ID_MES":str}, encoding="utf-8-sig")
    for frame, col in [(df,"ID_MES"),(df,"ID_ENTIDAD"),(states,"ID_ENTIDAD"),(months,"ID_MES")]:
        frame[col] = frame[col].str.zfill(2)
    df["ANIO"] = pd.to_numeric(df.ANIO, errors="raise").astype(int)
    df["date"] = pd.to_datetime(dict(year=df.ANIO, month=df.ID_MES.astype(int), day=1))
    for col in TECH:
        df[col] = pd.to_numeric(df[col],errors="raise")
        if (df[col] < 0).any():
            raise ValueError(f"Negative sales in {col}")
    if df.duplicated(["date","ID_ENTIDAD"]).any():
        raise ValueError("Duplicate month/state observations; check source vintages")
    df = df.merge(states[["ID_ENTIDAD","DESC_ENTIDAD"]], on="ID_ENTIDAD", how="left",validate="many_to_one")
    df = df.merge(months[["ID_MES","DESCRIPCION_MES"]], on="ID_MES", how="left",validate="many_to_one")
    if df[["DESC_ENTIDAD","DESCRIPCION_MES"]].isna().any().any():
        raise ValueError("Missing state/month catalog match")
    return df.sort_values(["date","ID_ENTIDAD"])

try:
    raw = load_data()
except (FileNotFoundError, ValueError, KeyError) as error:
    st.error(f"Data load error: {error}")
    st.stop()

latest = raw.date.max()
years = sorted(raw.ANIO.unique())

st.sidebar.title("Explore the story")
year_range = st.sidebar.slider("Years", min_value=min(years), max_value=max(years), value=(min(years),max(years)))
states_list = sorted(raw.loc[raw.ID_ENTIDAD!="99","DESC_ENTIDAD"].unique())
selected_states = st.sidebar.multiselect("States (blank = Mexico)", states_list)
selected_tech = st.sidebar.multiselect("Vehicle technology", ORDER, default=ORDER)
include_unknown = st.sidebar.checkbox("Include unspecified state in national totals",value=True)
st.sidebar.caption("For comparisons, 2026 includes data only through October. The dashboard compares equivalent calendar months.")
if not selected_tech:
    st.warning("Select at least one technology to continue.")
    st.stop()

base = raw[raw.ANIO.between(*year_range)].copy()
if selected_states:
    base = base[base.DESC_ENTIDAD.isin(selected_states)].copy()
elif not include_unknown:
    base = base[base.ID_ENTIDAD!="99"].copy()
selected_columns = [column for column,name in TECH.items() if name in selected_tech]
base["sales_total"] = base[selected_columns].sum(axis=1)
if base.empty:
    st.warning("No source observations in this selection.")
    st.stop()

long = base.melt(id_vars=["date","ANIO","ID_ENTIDAD","DESC_ENTIDAD","ESTATUS"],value_vars=selected_columns,var_name="code",value_name="sales")
long["technology"] = long.code.map(TECH)
monthly = long.groupby(["date","technology"],as_index=False).sales.sum()
monthly_total = monthly.groupby("date",as_index=False).sales.sum().sort_values("date")
focus_year = int(base.ANIO.max())
# Compare like-for-like months: cap at the latest month of that year actually available in the selected source.
focus_month = int(base.loc[base.ANIO==focus_year,"date"].dt.month.max())
focus_date = pd.Timestamp(focus_year,focus_month,1)
prev_year = focus_year-1
available_months = set(base.loc[base.ANIO==focus_year,"date"].dt.month.unique())
prev_months = set(base.loc[base.ANIO==prev_year,"date"].dt.month.unique())
comparable = (prev_year in set(base.ANIO)) and set(range(1,focus_month+1)).issubset(available_months & prev_months)
focus_sales = int(base.loc[(base.ANIO==focus_year)&(base.date.dt.month<=focus_month),"sales_total"].sum())
prev_sales = int(base.loc[(base.ANIO==prev_year)&(base.date.dt.month<=focus_month),"sales_total"].sum()) if comparable else None
yoy = ((focus_sales/prev_sales-1)*100) if comparable and prev_sales else None
focus_mix = long.loc[(long.ANIO==focus_year)&(long.date.dt.month<=focus_month)].groupby("technology").sales.sum().reindex(selected_tech,fill_value=0)
leader = focus_mix.idxmax() if focus_mix.sum()>0 else "N/A"
leader_share = (focus_mix.max()/focus_mix.sum()*100) if focus_mix.sum()>0 else 0
period_label = f"Jan–{focus_date.strftime('%b')} {focus_year}"

st.markdown('<div class="kicker">EL FINANCIERO · DATA JOURNALISM PROJECT</div>',unsafe_allow_html=True)
st.title("Mexico's electrified vehicle revolution")
st.markdown('<div class="deck">Sales of electrified vehicles have risen substantially, but not all technologies or states are moving at the same pace. Follow the evidence to see where the transition is happening—and what the numbers cannot tell us.</div>', unsafe_allow_html=True)
st.caption(f"INEGI RAIAVL · Monthly reported sales, January {min(years)}–{latest.strftime('%B %Y')} · Current analysis: {year_range[0]}–{year_range[1]}")
if selected_states or len(selected_tech)!=3 or year_range!=(min(years),max(years)):
    st.info("Filtered analysis: all charts and conclusions reflect the selected years, states, and vehicle technologies unless otherwise labeled.")

c1,c2,c3,c4 = st.columns(4)
c1.metric("Sales · selected years",f"{base.sales_total.sum():,}")
c2.metric(f"Sales · {period_label}",f"{focus_sales:,}")
c3.metric(f"Growth vs {prev_year} same months",f"{yoy:+.1f}%" if yoy is not None else "N/A")
c4.metric(f"Leading technology · {focus_year}",f"{leader_share:.1f}%",help=f"{leader}; share among selected technologies, not all cars")
st.caption("These figures measure reported HEV, PHEV and BEV sales—not total passenger-vehicle sales. A selected subset of technologies changes the denominator.")

def style(fig,height=390):
    fig.update_layout(template="plotly_white",height=height,margin=dict(l=10,r=25,t=45,b=25),
                      font=dict(color="#1B3445"),legend=dict(title="",orientation="h",y=1.15,x=0),
                      paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(gridcolor="#ECF0F3",zeroline=False)
    fig.update_yaxes(gridcolor="#ECF0F3",zeroline=False)
    st.plotly_chart(fig,use_container_width=True,config={"displaylogo":False})

def chapter(n,title,description):
    st.divider()
    st.markdown(f'<div class="kicker">CHAPTER {n}</div>',unsafe_allow_html=True)
    st.subheader(title)
    st.write(description)

def take(message):
    st.markdown(f'<div class="insight"><b>Why it matters:</b> {message}</div>',unsafe_allow_html=True)

chapter("01","A decade of expansion, with major disruptions along the way",
        "A rolling 12-month total makes long-term demand easier to understand despite seasonal variations.")
monthly_index = monthly_total.set_index("date").sales
# Require 12 recorded months; missing months remain NA and are never treated as zero.
month_grid = pd.date_range(monthly_index.index.min(), monthly_index.index.max(),freq="MS")
rolling = monthly_index.reindex(month_grid).rolling(12,min_periods=12).sum().dropna()
if len(rolling):
    fig = px.line(x=rolling.index,y=rolling.values,labels={"x":"Month","y":"Reported vehicles · trailing 12 months"})
    fig.update_traces(line=dict(color="#2563A6",width=3),hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>")
    for when,what in [("2020-03-01","Pandemic"),("2021-06-01","Global chip shortage"),("2026-01-01","Tariff policy change")]:
        point=pd.Timestamp(when)
        if rolling.index.min()<=point<=rolling.index.max():
            fig.add_vline(x=point.timestamp()*1000,line_color="#A6B3BE",line_dash="dot")
            fig.add_annotation(x=point.timestamp()*1000,y=1.02,yref="paper",text=what,showarrow=False,font_size=10)
    style(fig,440)
    first,last=float(rolling.iloc[0]),float(rolling.iloc[-1])
    take(f"The trailing annual total moved from <b>{first:,.0f}</b> to <b>{last:,.0f}</b> vehicles over the displayed window. Historical markers provide context, not proof of a causal effect.")
else:
    st.info("Select a time window with at least 12 consecutive reported months to see the rolling trend.")

chapter("02","Hybrids and fully electric vehicles are on different paths",
        "The line chart compares January through the same ending month in each year. The bar chart shows the latest selected year's sales mix.")
like = long.loc[long.date.dt.month<=focus_month].groupby(["ANIO","technology"],as_index=False).sales.sum()
fig=px.line(like,x="ANIO",y="sales",color="technology",markers=True,color_discrete_map=COLORS,
            category_orders={"technology":ORDER},labels={"ANIO":"Year","sales":f"Reported sales · Jan–{focus_date.strftime('%b')}","technology":"Technology"})
fig.update_traces(line_width=3,marker_size=7)
fig.update_xaxes(dtick=1)
style(fig,420)
st.caption(f"Same-month comparison: January–{focus_date.strftime('%B')} in each year; source periods must be interpreted with coverage caveats below.")
if focus_mix.sum()>0:
    share=(focus_mix/focus_mix.sum()*100).sort_values()
    mixdf=share.rename("share").reset_index().rename(columns={"index":"technology"})
    fig=px.bar(mixdf,x="share",y="technology",color="technology",orientation="h",text="share",
               color_discrete_map=COLORS,labels={"share":"Share of selected electrified sales (%)","technology":""})
    fig.update_traces(texttemplate="%{x:.1f}%",textposition="outside",showlegend=False,cliponaxis=False)
    fig.update_xaxes(range=[0,110],ticksuffix="%")
    style(fig,270)
    take(f"<b>{leader}</b> leads the selected mix with <b>{leader_share:.1f}%</b> of reported sales in <b>{period_label}</b>. This is not the share of all vehicle sales in Mexico.")

chapter("03","Mexico's transition is geographically uneven",
        "Rank states by reported vehicle volume, then compare each state's technology composition. Higher sales do not necessarily mean higher adoption per person.")
state_long=long.loc[long.ID_ENTIDAD!="99"].groupby(["DESC_ENTIDAD","technology"],as_index=False).sales.sum()
state_total=state_long.groupby("DESC_ENTIDAD").sales.sum().sort_values(ascending=False)
if not state_total.empty:
    top_n=st.slider("Number of states displayed",min_value=1,max_value=min(20,len(state_total)),value=min(10,len(state_total)))
    names=state_total.head(top_n).index.tolist()
    ranked=state_long[state_long.DESC_ENTIDAD.isin(names)].copy()
    fig=px.bar(ranked,x="sales",y="DESC_ENTIDAD",color="technology",orientation="h",barmode="stack",
               category_orders={"DESC_ENTIDAD":list(reversed(names)),"technology":ORDER},color_discrete_map=COLORS,
               labels={"sales":"Reported vehicles sold","DESC_ENTIDAD":"State"})
    fig.update_xaxes(rangemode="tozero")
    style(fig,max(350,top_n*36))
    take(f"<b>{names[0]}</b> recorded the most sales in the selected period (<b>{state_total.iloc[0]:,.0f}</b> vehicles). This ranking measures volume, not per-capita adoption.")
    if len(selected_tech)>1:
        pivot=ranked.pivot_table(index="DESC_ENTIDAD",columns="technology",values="sales",aggfunc="sum",fill_value=0)
        pivot=pivot.reindex(index=names,columns=selected_tech,fill_value=0)
        pct=pivot.div(pivot.sum(axis=1).replace(0,float("nan")),axis=0)*100
        fig=go.Figure(go.Heatmap(z=pct.values,x=pct.columns,y=pct.index,colorscale="Blues",zmin=0,zmax=100,
                                 hovertemplate="%{y}<br>%{x}: %{z:.1f}%<extra></extra>",colorbar=dict(title="%")))
        fig.update_yaxes(autorange="reversed")
        style(fig,max(330,top_n*30))
else:
    st.info("No state records match the current filters.")
st.caption("'No especificado' is not a state. It is excluded from state charts even when included in national totals.")

chapter("04","What the latest comparison suggests—and what to do next",
        "Year-over-year changes are calculated on identical months, and only where both years are available in your selected range.")
if comparable:
    current=like.loc[like.ANIO==focus_year].set_index("technology").sales.reindex(selected_tech,fill_value=0)
    previous=like.loc[like.ANIO==prev_year].set_index("technology").sales.reindex(selected_tech,fill_value=0)
    growth=(current/previous.replace(0,float("nan"))-1)*100
    growth_df=growth.dropna().rename("growth").reset_index().rename(columns={"index":"technology"})
    if not growth_df.empty:
        fig=px.bar(growth_df,x="growth",y="technology",orientation="h",color="technology",text="growth",
                   color_discrete_map=COLORS,labels={"growth":f"Change vs {prev_year} (%)","technology":""})
        fig.update_traces(texttemplate="%{x:+.1f}%",textposition="outside",showlegend=False,cliponaxis=False)
        fig.update_xaxes(zeroline=True,zerolinecolor="#768B99")
        style(fig,290)
        fastest=growth_df.loc[growth_df.growth.idxmax()]
        take(f"<b>{fastest.technology}</b> had the highest percentage growth in <b>{period_label}</b> versus the same months in {prev_year} (<b>{fastest.growth:+.1f}%</b>). Compare percentages with actual sales volumes before declaring a market leader.")
    else:
        st.info("Technology growth rates are undefined because the prior-year baseline is zero.")
    with st.expander("View exact comparable sales"):
        st.dataframe(pd.DataFrame({f"{prev_year} Jan–{focus_date.strftime('%b')}":previous,
                                   f"{focus_year} Jan–{focus_date.strftime('%b')}":current,
                                   "Growth (%)":growth.round(1)}),use_container_width=True)
else:
    st.info(f"To see year-over-year growth for {focus_year}, include {prev_year} and {focus_year} and ensure both have January–{focus_date.strftime('%B')} records.")

st.subheader("Editorial takeaway")
st.write("**For consumers:** Compare available technologies without confusing hybrids with fully electric cars. **For dealerships and automakers:** Use differences in reported sales and technology mix to guide further local market research. **For policymakers:** Combine these sales patterns with charging, income and population data before drawing infrastructure conclusions.")
with st.expander("Methodology, limitations, and coverage",expanded=True):
    st.markdown(f"""
- **Source:** INEGI RAIAVL, monthly hybrid and electric vehicle sales, January 2016–{latest.strftime('%B %Y')}. Latest supplied metadata: November 9, 2026.
- **Coverage:** Reported sales only; some manufacturers do not report (the assignment identifies BYD). Changes in the reporting panel can affect apparent growth.
- **Revisions:** `ESTATUS` is preserved. Recent figures may be revised in future releases.
- **Geography:** Unspecified state is excluded from rankings; it can be included in national totals with the sidebar checkbox.
- **Missing denominators:** This dataset does not establish the percentage of *all* cars sold that are electric. It does not include vehicle prices, imports by country, plant-level production, charging points, or population.
- **Incomplete 2026:** The latest source observation is {latest.strftime('%B %Y')}. Comparisons are restricted to the same months in each year.
- **Interpretation:** Event annotations do not prove causation. Zero observed sales and unreported sales are not necessarily the same.
""")
    statuses=base.ESTATUS.value_counts().rename_axis("Figure status").reset_index(name="Rows")
    st.dataframe(statuses,hide_index=True,use_container_width=True)
st.download_button("Download filtered source rows (CSV)",data=base.to_csv(index=False).encode("utf-8-sig"),file_name="mexico_ev_filtered.csv",mime="text/csv")
st.caption("Storytelling design: audience → evidence → explanation → implications. Built with pandas, Plotly and Streamlit.")
