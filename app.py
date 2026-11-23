"""Mexico's Electric Vehicle Revolution — explanatory data journalism dashboard.

Run locally: python3 -m streamlit run app.py
Source: INEGI RAIAVL monthly hybrid/electric vehicle sales, 2016–October 2026.
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Mexico's Electric Vehicle Revolution", page_icon="🚘", layout="wide")
DATA = Path(__file__).resolve().parent / "data"
TECH = {
    "VEH_HIBRIDAS": "Hybrid (HEV)",
    "VEH_HIBRIDAS_PLUGIN": "Plug-in hybrid (PHEV)",
    "VEH_ELECTR": "Fully electric (BEV)",
}
TECH_ORDER = list(TECH.values())
COLORS = {
    "Hybrid (HEV)": "#2267A5",           # blue
    "Plug-in hybrid (PHEV)": "#E58A36",  # orange
    "Fully electric (BEV)": "#1C986D",   # green
}
INK = "#162A3B"
MUTED = "#718096"

st.markdown("""<style>
.block-container {max-width: 1180px; padding-top: 1.6rem; padding-bottom: 3.5rem}
h1,h2,h3 {letter-spacing: -.025em}
h1 {font-weight: 760; line-height: 1.16}
[data-testid="stMetricValue"] {font-size: 1.8rem}
[data-testid="stMetricLabel"] {font-size: .9rem}
.story-kicker {font-size: .75rem; font-weight: 800; letter-spacing: .14em; color: #2267A5}
.story-deck {font-size: 1.15rem; line-height: 1.6; color: #52657A; max-width: 950px}
.story-insight {border-left: 3px solid #1C986D; padding: .55rem 1rem; background: rgba(28,152,109,.07); margin: .5rem 0 1.5rem}
.story-note {color:#718096; font-size: .83rem}
section[data-testid="stSidebar"] {border-right: 1px solid rgba(130,140,155,.2)}
</style>""", unsafe_allow_html=True)

@st.cache_data(show_spinner="Loading INEGI data...")
def load_data():
    paths = sorted(DATA.glob("raiavl_hibrido_mensual_tr_cifra_20*.csv"))
    if not paths:
        raise FileNotFoundError("Missing annual CSV files in data/ directory")
    raw = pd.concat(
        [pd.read_csv(path, encoding="utf-8-sig", dtype={"ID_MES":str,"ID_ENTIDAD":str}) for path in paths],
        ignore_index=True,
    )
    states = pd.read_csv(DATA / "tc_entidad_federativa.csv", encoding="utf-8-sig", dtype={"ID_ENTIDAD":str})
    months = pd.read_csv(DATA / "tc_mes.csv", encoding="utf-8-sig", dtype={"ID_MES":str})
    for df, col in [(raw,"ID_MES"),(raw,"ID_ENTIDAD"),(states,"ID_ENTIDAD"),(months,"ID_MES")]:
        df[col] = df[col].str.zfill(2)
    raw["ANIO"] = pd.to_numeric(raw["ANIO"], errors="raise").astype(int)
    raw["date"] = pd.to_datetime(dict(year=raw.ANIO,month=raw.ID_MES.astype(int),day=1))
    for col in TECH:
        raw[col] = pd.to_numeric(raw[col],errors="raise")
    if raw.duplicated(["date","ID_ENTIDAD"]).any():
        raise ValueError("Duplicate month/state rows: check dataset vintages")
    raw = raw.merge(states[["ID_ENTIDAD","DESC_ENTIDAD"]],on="ID_ENTIDAD",how="left",validate="many_to_one")
    raw = raw.merge(months[["ID_MES","DESCRIPCION_MES"]],on="ID_MES",how="left",validate="many_to_one")
    if raw[["DESC_ENTIDAD","DESCRIPCION_MES"]].isna().any().any():
        raise ValueError("Unmatched month or state code")
    raw["total"] = raw[list(TECH)].sum(axis=1)
    return raw

try:
    raw = load_data()
except (FileNotFoundError, ValueError, KeyError) as exc:
    st.error(f"Could not load the dataset: {exc}")
    st.stop()

last_date = raw.date.max()
last_year, last_month = last_date.year, last_date.month
last_month_name = last_date.strftime("%B")


def nfmt(n):
    return f"{n:,.0f}"


def pformat(n):
    return "N/A" if pd.isna(n) else f"{n:+.1f}%"


def tidy(fig, height=400, unified=False):
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=8,r=15,t=45,b=25),
        font=dict(family="Arial, sans-serif", color=INK, size=12),
        legend=dict(title="",orientation="h",y=1.09,x=0),
        hovermode="x unified" if unified else "closest",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showline=False, gridcolor="#E9EFF3", zeroline=False)
    fig.update_yaxes(showline=False, gridcolor="#E9EFF3", zeroline=False)
    return fig


def show(fig, height=400, unified=False):
    st.plotly_chart(tidy(fig,height,unified),use_container_width=True,config={"displaylogo":False})


def section(number, headline, context):
    st.divider()
    st.markdown(f'<div class="story-kicker">CHAPTER {number}</div>', unsafe_allow_html=True)
    st.subheader(headline)
    st.write(context)


def insight(message):
    st.markdown(f'<div class="story-insight">{message}</div>', unsafe_allow_html=True)


st.sidebar.markdown("## Explore the data")
st.sidebar.caption("Changing filters recalculates every headline and chart.")
years = sorted(raw.ANIO.unique())
year_range = st.sidebar.slider("Years",min_value=min(years),max_value=max(years),value=(min(years),max(years)))
state_choices = sorted(raw.loc[raw.ID_ENTIDAD != "99","DESC_ENTIDAD"].unique())
chosen_states = st.sidebar.multiselect("Mexican states",state_choices,placeholder="All states (national view)")
chosen_techs = st.sidebar.multiselect("Vehicle technology",TECH_ORDER,default=TECH_ORDER)
include_unspecified = st.sidebar.checkbox("Include unspecified geography in national totals",True)
if not chosen_techs:
    st.warning("Select at least one vehicle technology in the sidebar.")
    st.stop()

base = raw[raw.ANIO.between(*year_range)].copy()
if chosen_states:
    base = base[base.DESC_ENTIDAD.isin(chosen_states)].copy()
elif not include_unspecified:
    base = base[base.ID_ENTIDAD != "99"].copy()
selected_cols = [col for col, label in TECH.items() if label in chosen_techs]
base["selected_total"] = base[selected_cols].sum(axis=1)
long = base.melt(id_vars=["date","ANIO","ID_ENTIDAD","DESC_ENTIDAD","ESTATUS"],value_vars=selected_cols,var_name="variable",value_name="sales")
long["technology"] = long.variable.map(TECH)
monthly = long.groupby(["date","technology"],as_index=False).sales.sum()
totals_monthly = monthly.groupby("date",as_index=False).sales.sum().sort_values("date")

st.markdown('<div class="story-kicker">EL FINANCIERO  /  AUTOMOTIVE DATA STORY</div>',unsafe_allow_html=True)
st.title("Mexico's electric vehicle revolution")
st.markdown('<div class="story-deck">Electrified vehicle sales are rising. But behind the growth is a more surprising story: traditional hybrids, not fully electric cars, still lead the transition. Explore who is buying, what technologies are gaining ground, and where change is concentrated.</div>',unsafe_allow_html=True)
st.caption(f"A data journalism analysis for Mexican consumers and automotive decision-makers · INEGI RAIAVL · January 2016–{last_month_name} {last_year}")
if chosen_states or len(chosen_techs)<3 or year_range != (min(years),max(years)):
    st.info("**Filtered view:** All findings below refer to your current state, technology, and year selections.")

# Shared YoY calendar window respects the dataset's most recent month and the selected year range.
current_ytd = base[(base.ANIO==last_year)&(base.date.dt.month<=last_month)].selected_total.sum()
previous_ytd = base[(base.ANIO==last_year-1)&(base.date.dt.month<=last_month)].selected_total.sum()
yoy = (current_ytd/previous_ytd-1)*100 if previous_ytd else float("nan")
all_sales = base.selected_total.sum()
latest_tech = long[(long.ANIO==last_year)&(long.date.dt.month<=last_month)].groupby("technology").sales.sum().sort_values(ascending=False)
leader = latest_tech.index[0] if not latest_tech.empty else None
leader_share = 100*latest_tech.iloc[0]/latest_tech.sum() if len(latest_tech) and latest_tech.sum() else float("nan")

st.markdown("#### At a glance")
m1,m2,m3,m4 = st.columns(4)
m1.metric("Sales in selected years",nfmt(all_sales))
m2.metric(f"{last_year} Jan–{last_date.strftime('%b')} sales",nfmt(current_ytd) if last_year in year_range else "N/A")
m3.metric("Same-period annual growth",pformat(yoy) if last_year-1>=year_range[0] else "N/A")
m4.metric("Leading technology share",f"{leader_share:.1f}%" if leader else "N/A")
st.caption("Reported HEV + PHEV + BEV sales only; not total Mexican automotive sales. Latest year is incomplete.")

# 01: long-run growth and a valid year-by-year calendar comparison.
section("01", "The market grew — but the pandemic interrupted its climb", "A trailing 12-month total helps reveal long-run direction without confusing seasonal sales fluctuations with lasting change.")
rolling = totals_monthly.set_index("date").asfreq("MS")["sales"].rolling(12,min_periods=12).sum().dropna().reset_index(name="rolling_sales")
if not rolling.empty:
    fig=px.line(rolling,x="date",y="rolling_sales",labels={"date":"Month","rolling_sales":"Sales · trailing 12 months"})
    fig.update_traces(line=dict(color="#2267A5",width=3),hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>")
    for date,label in [("2020-03-01","Pandemic"),("2021-06-01","Chip shortage period"),("2026-01-01","Tariff change")]:
        d = pd.Timestamp(date)
        if rolling.date.min()<=d<=rolling.date.max():
            fig.add_vline(x=d.timestamp()*1000,line_dash="dot",line_color="#9BA8B4",annotation_text=label,annotation_position="top left",annotation_font_size=10)
    show(fig,430,True)
    first_value,last_value=rolling.rolling_sales.iloc[0],rolling.rolling_sales.iloc[-1]
    if first_value>0:
        insight(f"<b>What matters:</b> Over the selected rolling period, reported annualized sales moved from <b>{nfmt(first_value)}</b> to <b>{nfmt(last_value)}</b> vehicles. The annotated events provide context, not evidence of causality.")
else:
    st.info("Choose at least 12 consecutive months of data to display the rolling trend.")

# 02: technology growth, fair partial-year comparison, and composition.
section("02", "The electrification story is still mostly a hybrid story", "Compare technologies over the same months. Conventional hybrids (HEV) do not plug in; PHEVs plug in and also use an engine; BEVs are fully electric.")
compare_month = last_month if last_month<12 else 12
like = long[long.date.dt.month<=compare_month].groupby(["ANIO","technology"],as_index=False).sales.sum()
like["period"] = like.ANIO.astype(str)
fig=px.line(like,x="ANIO",y="sales",color="technology",markers=True,
    category_orders={"technology":TECH_ORDER},color_discrete_map=COLORS,
    labels={"ANIO":"Year","sales":f"Sales · Jan–{last_date.strftime('%b')} each year","technology":"Technology"})
fig.update_traces(line_width=3,marker_size=7)
fig.update_xaxes(dtick=1)
show(fig,420,True)
st.caption(f"**Apples-to-apples comparison:** Every year is limited to January–{last_month_name}, matching the available months in {last_year}. Filtered years with no source rows are not filled with invented sales.")

mix = like[like.ANIO==last_year].copy()
if not mix.empty and mix.sales.sum()>0:
    mix["share"] = mix.sales/mix.sales.sum()*100
    mix= mix.sort_values("share",ascending=True)
    fig=px.bar(mix,x="share",y="technology",orientation="h",text="share",color="technology",color_discrete_map=COLORS,
        labels={"share":f"Share of selected technologies in {last_year} (%)","technology":""})
    fig.update_traces(texttemplate="%{x:.1f}%",textposition="outside",showlegend=False,cliponaxis=False)
    fig.update_xaxes(range=[0,max(100,mix.share.max()*1.12)],ticksuffix="%",showgrid=False)
    fig.update_yaxes(showgrid=False)
    show(fig,270)
    leader_row=mix.loc[mix.share.idxmax()]
    insight(f"<b>What matters:</b> <b>{leader_row.technology}</b> represents <b>{leader_row.share:.1f}%</b> of recorded electrified-vehicle sales in January–{last_month_name} {last_year} for the current selection. That is a share <i>within these technologies</i>, not the share of all new vehicles.")
else:
    st.info("Select a range including the latest year to display the latest technology mix.")

# 03: geography: ranking + share by technology, while excluding unspecified from state ranking.
section("03", "The transition looks very different across Mexico", "Which states account for the most reported sales, and what is their technology mix? Absolute volumes can reflect population and market size — they do not measure per-capita adoption.")
state_long=long[long.ID_ENTIDAD!="99"].groupby(["DESC_ENTIDAD","technology"],as_index=False).sales.sum()
state_totals=state_long.groupby("DESC_ENTIDAD").sales.sum().sort_values(ascending=False)
if not state_totals.empty:
    top_count=st.slider("Show leading states",5,min(20,len(state_totals)),10)
    leaders=state_totals.head(top_count).index.tolist()
    top_state=state_long[state_long.DESC_ENTIDAD.isin(leaders)].copy()
    order=list(reversed(leaders))
    fig=px.bar(top_state,x="sales",y="DESC_ENTIDAD",color="technology",orientation="h",barmode="stack",
        category_orders={"DESC_ENTIDAD":order,"technology":TECH_ORDER},color_discrete_map=COLORS,
        labels={"sales":"Reported vehicles sold","DESC_ENTIDAD":"State"})
    fig.update_yaxes(showgrid=False)
    fig.update_xaxes(rangemode="tozero")
    show(fig,max(390,top_count*37),False)
    top_state_name=state_totals.index[0]
    insight(f"<b>What matters:</b> <b>{top_state_name}</b> leads the selected geography with <b>{nfmt(state_totals.iloc[0])}</b> reported vehicles. A large total is not necessarily the highest adoption rate.")
    if len(state_totals)>=2:
        st.markdown("**Geographic composition:** Does the leading state's mix resemble the others?")
        cross=top_state.pivot(index="DESC_ENTIDAD",columns="technology",values="sales").fillna(0)
        cross=cross.reindex(index=leaders,columns=chosen_techs,fill_value=0)
        cross = cross.div(cross.sum(axis=1).replace(0,float('nan')),axis=0).mul(100).fillna(0)
        heat=go.Figure(go.Heatmap(z=cross.values,x=cross.columns.tolist(),y=cross.index.tolist(),colorscale="Blues",
            zmin=0,zmax=100,hovertemplate="%{y}<br>%{x}: %{z:.1f}%<extra></extra>",colorbar=dict(title="%")))
        heat.update_yaxes(autorange="reversed",showgrid=False)
        show(heat,max(350,len(cross)*29))
else:
    st.info("No state records match this selection.")
st.caption("'No especificado' is omitted from state rankings and heatmaps, even if included in national totals.")

# 04: actionable and defensible synthesis.
section("04", "What's changing fastest — and what does it mean?", "The latest comparable year-to-date growth rates reveal where sales are accelerating, without assuming that growth will continue indefinitely.")
pair=like[like.ANIO.isin([last_year-1,last_year])].pivot(index="technology",columns="ANIO",values="sales")
if last_year in year_range and last_year-1 in year_range and set([last_year-1,last_year]).issubset(pair.columns):
    pair=pair.reindex(chosen_techs)
    comparison=pair.copy()
    comparison["growth"]=(comparison[last_year]/comparison[last_year-1].replace(0,float('nan'))-1)*100
    growth_chart=comparison.dropna(subset=["growth"]).reset_index().rename(columns={"index":"technology"})
    if not growth_chart.empty:
        fig=px.bar(growth_chart,x="growth",y="technology",orientation="h",color="technology",color_discrete_map=COLORS,
            text="growth",labels={"growth":"Growth vs same period last year (%)","technology":""})
        fig.update_traces(texttemplate="%{x:+.1f}%",textposition="outside",showlegend=False,cliponaxis=False)
        fig.update_xaxes(zeroline=True,zerolinecolor="#84909A",showgrid=True)
        fig.update_yaxes(showgrid=False)
        show(fig,300)
        fastest=growth_chart.loc[growth_chart.growth.idxmax()]
        insight(f"<b>The takeaway:</b> <b>{fastest.technology}</b> registered the fastest year-over-year percentage growth (<b>{fastest.growth:+.1f}%</b>) in the selected technologies. Evaluate growth <i>together with sales volume</i> before inferring market leadership.")
    with st.expander("Exact year-to-date numbers"):
        st.dataframe(comparison.rename(columns={last_year-1:f"{last_year-1} sales",last_year:f"{last_year} sales","growth":"YoY change (%)"}),use_container_width=True)
else:
    st.info(f"Include both {last_year-1} and {last_year} in the year filter for a valid year-over-year comparison.")

st.markdown("#### What readers should do with these findings")
st.write("**Consumers:** Understand the difference between hybrid and fully electric adoption. **Automotive companies:** Compare technology demand and geographic sales concentration before planning distribution. **Policymakers:** Treat these sales patterns as a starting point — not a substitute for charging-infrastructure, population, or income data.")

with st.expander("Source notes, reporting gaps & methodological limits",expanded=True):
    st.markdown(f"""
- **Data:** INEGI, *Registro Administrativo de la Industria Automotriz de Vehículos Ligeros* (RAIAVL), monthly hybrid/electric vehicle sales, January 2016–{last_month_name} {last_year}. The uploaded metadata was modified on November 9, 2026.
- **Reporting coverage:** Some manufacturers do not report to the registry (the assignment identifies BYD as an example). These are reported sales, **not** a comprehensive market census. Changes to the reporting panel may affect trends.
- **Status:** Source includes definitive and revised figures. Revised figures can change in later INEGI releases; the dashboard preserves each row's original `ESTATUS`.
- **What is missing:** This table does not contain vehicle prices, battery range, buyer demographics, import origin, charging infrastructure, plant production, or the denominator of **all** new light-vehicle sales. It cannot establish nationwide BEV market share.
- **Unspecified geography:** Included in nationwide totals when the sidebar setting is enabled; excluded from state comparisons.
- **2026 is incomplete:** All cross-year charts use the same January–{last_month_name} period. The 12-month total instead uses complete trailing windows.
- **Events vs causation:** Pandemic, chip-shortage, and tariff annotations show context; these data cannot isolate effects of those events.
- **No invented observations:** Missing state/month records are not imputed; the rolling chart requires all months of its window.
""")
    counts=base.ESTATUS.value_counts().rename_axis("Original figure status").reset_index(name="Rows")
    st.dataframe(counts,hide_index=True,use_container_width=True)

st.download_button("Download filtered records (CSV)",data=base.to_csv(index=False).encode("utf-8-sig"),file_name="mexico_electrified_sales_filtered.csv",mime="text/csv")
st.caption("Data source: INEGI RAIAVL · Dashboard calculations: pandas · Visualizations: Plotly · Storytelling approach: audience, insight-led titles, emphasis, comparable time windows and explicit caveats.")
