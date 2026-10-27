"""
7주차 1번 수업 — 시작 코드 (필터 없음)
6주차 시각화 리포트와 같은 형태입니다. 오늘 여기에 필터를 붙여 대시보드로 만듭니다.
"""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="사용자 행동 탐색 대시보드", layout="wide")
st.title("사용자 행동 탐색 대시보드")
st.caption("주별 세션 퍼널 | 플랫폼 · 유입 경로별 | 2025.07 ~ 2026.06")

# ------------------------------------------------------------
# 0. 필요한 데이터만 추출 — 쓸 테이블과 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 처음 한 번만 만듦
# ------------------------------------------------------------
DATA_DIR = "data"                         # 원본 CSV를 넣어 둔 폴더
NEEDED = {                                 # 이번 대시보드에 필요한 테이블과 컬럼
    "app_events": ["event_id", "event_datetime", "customer_id", "session_id",
                   "event_name", "platform", "traffic_source"],
}

@st.cache_resource
def get_db():                             # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 만듦 (처음 한 번만)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name, cols in NEEDED.items():
        pd.read_csv(f"{DATA_DIR}/{name}.csv", usecols=cols).to_sql(name, con, index=False)
    # 5주차 제외 규칙: QA 계정 제외 · 중복 이벤트 제거
    con.execute("""
        CREATE TABLE events AS
        SELECT event_id, event_datetime, customer_id, session_id, event_name, platform, traffic_source
          FROM (SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY session_id, event_datetime, event_name
                                          ORDER BY event_id) AS dup
                  FROM app_events
                 WHERE customer_id NOT LIKE 'QA%')
         WHERE dup = 1
    """)
    # 세션별로 묶는 집계가 빨라지도록 session_id에 인덱스를 붙임 (없으면 첫 실행이 몇 분 걸릴 수 있음)
    con.execute("CREATE INDEX idx_events_session ON events(session_id)")
    return con

# ------------------------------------------------------------
# 1. 데이터 준비 — 정제된 events 테이블을 SQL로 집계
# ------------------------------------------------------------
@st.cache_data
def query(sql):                            # SQL을 실행해 표로 돌려줌
    return pd.read_sql(sql, get_db())

# 주 × 플랫폼 × 유입 경로별 세션 퍼널
SQL_WEEKLY_FUNNEL = """
WITH s AS (                                -- 세션의 첫 이벤트로 플랫폼 · 유입 경로 · 주 정하기
    SELECT session_id, platform, traffic_source,
           DATE(MIN(event_datetime), 'weekday 0', '-6 days') AS 주시작일
      FROM events
     GROUP BY session_id
)
SELECT s.주시작일,
       s.platform     AS 플랫폼,
       s.traffic_source AS 유입경로,
       COUNT(DISTINCT e.session_id)                                                    AS 세션수,
       COUNT(DISTINCT CASE WHEN e.event_name = 'view_restaurant' THEN e.session_id END)   AS 조회세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'add_to_cart'    THEN e.session_id END)   AS 장바구니세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'begin_checkout'  THEN e.session_id END)   AS 결제시작세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'order_complete'  THEN e.session_id END)   AS 주문세션,
       SUM(CASE WHEN e.event_name = 'payment_fail' THEN 1 ELSE 0 END)                     AS 결제실패
  FROM events e
  JOIN s ON e.session_id = s.session_id
 WHERE s.주시작일 < '2026-06-29'            -- 이틀치뿐인 마지막 주 제외
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    data = query(SQL_WEEKLY_FUNNEL)
    data["주시작일"] = pd.to_datetime(data["주시작일"]).dt.date
    return data

df = load_data()                         # 주 × 플랫폼 × 유입 경로별 세션 퍼널

AI_NOTES = {
    "전체": "총 세션수는 28,840개이며 주문 전환율은 14.5%, 가장 낮은 단계 전환율은 조회세션에서 장바구니세션으로 이어지는 단계의 41.4%다. 전체 평균 결제 전환율은 80.5% 수준을 기록했다. 이 퍼널 구조는 초기 탐색 단계에서 이탈이 가장 빈번히 일어나는 구조로 보인다.",
    "Android": "총 세션수는 16,053개이며 주문 전환율은 14.3%, 결제 전환율은 76.8%, 가장 낮은 단계 전환율은 41.8%였다. 전체 평균과 유사한 흐름을 보였으나 2026-04-13 주부터 2026-05-25 주까지 결제 전환율 하락과 결제실패 증가가 집중적으로 관측됐다. 해당 기간 외부 요인에 따른 결제 프로세스 이상 여부의 확인이 필요하다.",
    "iOS": "총 세션수는 12,787개이며 주문 전환율은 14.8%, 결제 전환율은 85.5%, 가장 낮은 단계 전환율은 40.8%였다. Android 대비 결제 전환율이 전반적으로 높게 유지되었으며 2025년 하반기 범위와 유사한 안정세를 보였다. iOS 환경은 결제 완료 단계까지의 안정성이 비교적 높게 유지된 것으로 보인다.",
    "organic": "총 세션수는 22,489개로 전체 유입의 대다수를 차지하며 주문 전환율은 16.0%, 결제 전환율은 80.4%, 가장 낮은 단계 전환율은 41.4%였다. 전체 평균 대비 주문 전환율이 소폭 높고 안정적인 유입 효율을 나타냈다. 자연 유입 사용자의 서비스 관여도가 상대적으로 견조했던 것으로 보인다.",
    "paid_ad": "총 세션수는 1,595개이며 주문 전환율은 26.3%, 결제 전환율은 90.3%, 가장 낮은 단계 전환율은 53.7%였다. 다른 유입경로와 비교해 모든 퍼널 단계별 전환율과 주문 전환율이 가장 높았다. 광고를 통해 유입된 사용자의 구매 의도가 매우 뚜렷했던 것으로 보인다.",
    "push": "총 세션수는 4,635개이며 주문 전환율은 3.2%, 결제 전환율은 63.8%, 가장 낮은 단계 전환율은 세션수에서 조회세션으로 이어진 단계의 28.4%였다. 다른 집단과 달리 첫 단계인 조회 진입 전환율이 가장 낮았으며 2026-02-02 주차부터 처음 등장했다. 푸시 메시지를 통한 초기 유입 유도 방식의 효과성 검토가 필요하다.",
    "referral": "총 세션수는 121개로 집단 크기(세션 수)가 500개 미만이며 주문 전환율은 0.0%, 결제 전환율은 0.0%, 가장 낮은 단계 전환율은 결제시작세션에서 주문세션으로 이어진 단계의 0.0%였다. 다른 집단과 달리 결제시작 단계 이후 주문으로 전환된 세션이 전혀 존재하지 않았다. 표본 수가 극히 적어 구조적 문제인지 단순 표본 오차인지 확인이 필요하다."
}

AI_SOURCE = "bot: Gemini가 미리 만든 해설 · 전체 기간 기준"

# ------------------------------------------------------------
# 1-1. 사이드바 필터
# ------------------------------------------------------------
st.sidebar.header("필터")

weeks = sorted(df["주시작일"].unique())
start_w, end_w = st.sidebar.select_slider(
    "기간",
    options=weeks,
    value=(weeks[0], weeks[-1]),
)

platforms = sorted(df["플랫폼"].unique())
sel_platforms = st.sidebar.multiselect("플랫폼", options=platforms, default=platforms)

sources = sorted(df["유입경로"].unique())
sel_sources = st.sidebar.multiselect("유입 경로", options=sources, default=sources)

base_start_w, base_end_w = st.sidebar.select_slider(
    "평소 범위 기준 기간",
    options=weeks,
    value=(weeks[0], weeks[min(25, len(weeks) - 1)]),
    help="문제가 없던 기간을 고르세요. 이 기간의 주별 값 범위를 '평소 범위'로 씁니다.",
)

# 집단 조건(플랫폼·유입경로)만 적용한 데이터 g
g = df[
    (df["플랫폼"].isin(sel_platforms))
    & (df["유입경로"].isin(sel_sources))
]

# g에 기간 조건을 더해 만든 데이터 f
f = g[
    (g["주시작일"] >= start_w)
    & (g["주시작일"] <= end_w)
]

# 사이드바 다운로드 영역 추가
st.sidebar.html("<hr style='margin: 20px 0;'>")
dl_c1, dl_c2 = st.sidebar.columns(2)
dl_c1.download_button(
    "전체 다운로드",
    df.to_csv(index=False, encoding="utf-8-sig"),
    "전체_데이터.csv",
    "text/csv",
)
dl_c2.download_button(
    "부분 다운로드",
    f.to_csv(index=False, encoding="utf-8-sig"),
    "필터적용_데이터.csv",
    "text/csv",
)

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()

# ------------------------------------------------------------
# 2. KPI 카드
# ------------------------------------------------------------
def rate(a, b):
    return a / b * 100 if b else 0

t = f[["세션수", "결제시작세션", "주문세션"]].sum()
c1, c2, c3 = st.columns(3)
c1.metric("세션 수", f"{t['세션수']:,}개")
c2.metric("주문 전환율 (방문 → 주문)", f"{rate(t['주문세션'], t['세션수']):.1f}%")
c3.metric("결제 전환율 (결제 시작 → 주문)", f"{rate(t['주문세션'], t['결제시작세션']):.1f}%")

# ------------------------------------------------------------
# 2-1. 규칙 기반 설명 문장 2개
# ------------------------------------------------------------
f_weekly = f.groupby("주시작일", as_index=False)[["세션수", "결제시작세션", "주문세션"]].sum().sort_values("주시작일")
g_base = g[(g["주시작일"] >= base_start_w) & (g["주시작일"] <= base_end_w)]
g_base_weekly = g_base.groupby("주시작일", as_index=False)[["세션수", "결제시작세션", "주문세션"]].sum().sort_values("주시작일")

def make_rule_msg(label, num_col, den_col):
    if len(f_weekly) < 4:
        return f"**{label}**: 비교하려면 선택 기간을 4주 이상 골라 주세요."
    
    valid_base = g_base_weekly[g_base_weekly[den_col] > 0]
    if len(valid_base) < 4:
        return f"**{label}**: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요."
    
    last4 = f_weekly.tail(4)
    start_4w = last4["주시작일"].iloc[0]
    curr_val = rate(last4[num_col].sum(), last4[den_col].sum())
    
    base_rates = valid_base[num_col] / valid_base[den_col] * 100
    low, high = base_rates.min(), base_rates.max()
    
    if curr_val < low:
        diff = low - curr_val
        return (
            f"**{label}**: {start_4w} 주부터 4주 동안 **{curr_val:.1f}%**로, "
            f"평소 범위({low:.1f}% ~ {high:.1f}%)보다 **{diff:.1f}%p** 낮습니다."
        )
    elif curr_val > high:
        diff = curr_val - high
        return (
            f"**{label}**: {start_4w} 주부터 4주 동안 **{curr_val:.1f}%**로, "
            f"평소 범위({low:.1f}% ~ {high:.1f}%)보다 **{diff:.1f}%p** 높습니다."
        )
    else:
        return (
            f"**{label}**: {start_4w} 주부터 4주 동안 **{curr_val:.1f}%**로, "
            f"평소 범위({low:.1f}% ~ {high:.1f}%) 안에 있습니다."
        )

st.info(make_rule_msg("결제 전환율", "주문세션", "결제시작세션"))
st.info(make_rule_msg("주문 전환율", "주문세션", "세션수"))
st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {base_start_w} ~ {base_end_w} (주별 값)")

with st.expander("🤖 AI 해설 · 전체", expanded=False):
    st.write(AI_NOTES.get("전체", "이 집단의 해설은 아직 없습니다."))
st.caption(AI_SOURCE)

st.divider()

# ------------------------------------------------------------
# 3. 차트
# ------------------------------------------------------------
left, right = st.columns(2)

# 3-1. 주별 결제 전환율 (플랫폼별)
wp = f.groupby(["주시작일", "플랫폼"])[["결제시작세션", "주문세션"]].sum().reset_index()
wp["결제전환율"] = (wp["주문세션"] / wp["결제시작세션"] * 100).round(1)
fig1 = px.line(wp, x="주시작일", y="결제전환율", color="플랫폼", markers=True,
               title="주별 결제 전환율 (플랫폼별)")
fig1.update_layout(yaxis_title="결제 전환율 (%)", xaxis_title="")
left.plotly_chart(fig1, width="stretch")

# 3-2. 세션 퍼널
steps = {"1.방문": "세션수", "2.식당조회": "조회세션", "3.장바구니": "장바구니세션",
         "4.결제시작": "결제시작세션", "5.주문완료": "주문세션"}
fun = pd.DataFrame({"단계": list(steps), "세션수": [f[c].sum() for c in steps.values()]})
fig2 = px.funnel(fun, x="세션수", y="단계", title="세션 퍼널")
right.plotly_chart(fig2, width="stretch")

# 3-3. 유입 경로별 주문 전환율
ws = f.groupby("유입경로")[["세션수", "주문세션"]].sum().reset_index()
ws["주문전환율"] = (ws["주문세션"] / ws["세션수"] * 100).round(1)
ws = ws.sort_values("주문전환율")
fig3 = px.bar(ws, x="주문전환율", y="유입경로", orientation="h", text_auto=".1f",
              hover_data=["세션수"], title="유입 경로별 주문 전환율")
fig3.update_xaxes(range=[0, ws["주문전환율"].max() * 1.2])
fig3.update_layout(xaxis_title="주문 전환율 (%)", yaxis_title="")
st.plotly_chart(fig3, width="stretch")

# ------------------------------------------------------------
# 4. 집단 비교
# ------------------------------------------------------------
st.divider()
st.subheader("집단 비교")

group_col = st.radio("비교 기준", options=["플랫폼", "유입경로"], horizontal=True)

step_cols = list(steps.values())
step_names = list(steps.keys())
grp = f.groupby(group_col, as_index=False)[step_cols].sum()

# 세션 수 500개 미만 집단 안내
small_groups = grp[grp["세션수"] < 500][group_col].tolist()
if small_groups:
    st.caption(
        f"⚠️ 세션 수가 500개 미만인 집단({', '.join(map(str, small_groups))})이 포함되어 있어 값이 크게 흔들릴 수 있습니다."
    )

cum_rows = []
step_rows = []

for _, row in grp.iterrows():
    g_name = row[group_col]
    base_sessions = row["세션수"]

    # 1) 누적 전환율 데이터 (첫 단계 대비 %)
    for s_name, s_col in steps.items():
        s_val = row[s_col]
        cum_rate = round(s_val / base_sessions * 100, 1) if base_sessions > 0 else 0.0
        cum_rows.append(
            {
                group_col: g_name,
                "단계": s_name,
                "누적전환율": cum_rate,
                "세션수": int(s_val),
            }
        )

    # 2) 단계 전환율 데이터 (직전 단계 대비 %)
    for i in range(1, len(step_cols)):
        prev_col = step_cols[i - 1]
        curr_col = step_cols[i]
        prev_val = row[prev_col]
        curr_val = row[curr_col]
        s_rate = round(curr_val / prev_val * 100, 1) if prev_val > 0 else 0.0
        step_rows.append(
            {
                group_col: g_name,
                "단계": f"{step_names[i - 1]} → {step_names[i]}",
                "단계전환율": s_rate,
                "기준세션": int(prev_val),
                "도달세션": int(curr_val),
            }
        )

cum_df = pd.DataFrame(cum_rows)
step_df = pd.DataFrame(step_rows)

comp_left, comp_right = st.columns(2)

# 왼쪽: 누적 전환율(%) 퍼널
fig4 = px.funnel(
    cum_df,
    x="누적전환율",
    y="단계",
    color=group_col,
    hover_data=["세션수"],
    title=f"{group_col}별 누적 전환율 퍼널 (방문 대비 %)",
)
fig4.update_layout(xaxis_title="누적 전환율 (%)", yaxis_title="")
comp_left.plotly_chart(fig4, width="stretch")

# 오른쪽: 단계 전환율(%) 막대
fig5 = px.bar(
    step_df,
    x="단계",
    y="단계전환율",
    color=group_col,
    barmode="group",
    text_auto=".1f",
    hover_data=["기준세션", "도달세션"],
    title=f"{group_col}별 단계 전환율 (직전 단계 대비 %)",
)
fig5.update_yaxes(range=[0, step_df["단계전환율"].max() * 1.2])
fig5.update_layout(xaxis_title="", yaxis_title="단계 전환율 (%)")
comp_right.plotly_chart(fig5, width="stretch")

# ------------------------------------------------------------
# 5. 드릴다운: 언제부터, 무엇 때문일까
# ------------------------------------------------------------
st.divider()
st.subheader("드릴다운: 언제부터, 무엇 때문일까")

dd_col1, dd_col2 = st.columns(2)

available_groups = sorted(f[group_col].unique())
target_group = dd_col1.selectbox("자세히 볼 집단", options=available_groups)

drill_steps = {
    "방문 → 식당조회": ("세션수", "조회세션"),
    "식당조회 → 장바구니": ("조회세션", "장바구니세션"),
    "장바구니 → 결제시작": ("장바구니세션", "결제시작세션"),
    "결제시작 → 주문": ("결제시작세션", "주문세션"),
}
target_step = dd_col2.selectbox("단계", options=list(drill_steps.keys()))

other_col = "유입경로" if group_col == "플랫폼" else "플랫폼"
prev_c, curr_c = drill_steps[target_step]

# 차트 ① (위): 고른 집단만 남긴 뒤, 다른 축으로 쪼개어 주별 전환율 선 차트
f_target = f[f[group_col] == target_group]
dd_weekly = f_target.groupby(["주시작일", other_col], as_index=False)[[prev_c, curr_c]].sum()
dd_weekly["전환율"] = (
    dd_weekly[curr_c] / dd_weekly[prev_c].where(dd_weekly[prev_c] > 0) * 100
).round(1)

fig6 = px.line(
    dd_weekly,
    x="주시작일",
    y="전환율",
    color=other_col,
    markers=True,
    title=f"① {target_group}의 주별 {target_step} 전환율 — {other_col}별로 쪼개 보기",
)
fig6.update_layout(xaxis_title="", yaxis_title="전환율 (%)")
st.plotly_chart(fig6, width="stretch")
st.caption("모든 갈래가 같은 시점에 함께 움직였다면, 그 축은 원인이 아닙니다.")

# 차트 ② (아래): 주별 결제실패 건수 (고른 집단 vs 그 외)
fail_df = f.assign(
    구분=f[group_col].where(f[group_col] == target_group, "그 외")
)
fail_weekly = fail_df.groupby(["주시작일", "구분"], as_index=False)["결제실패"].sum()

fig7 = px.bar(
    fail_weekly,
    x="주시작일",
    y="결제실패",
    color="구분",
    barmode="group",
    category_orders={"구분": [target_group, "그 외"]},
    color_discrete_map={target_group: "#D62728", "그 외": "#B0B0B0"},
    title=f"② 주별 결제실패 건수 — {target_group} vs 그 외",
)
fig7.update_layout(xaxis_title="", yaxis_title="결제실패 건수")
st.plotly_chart(fig7, width="stretch")
st.caption("문제가 생긴 시점과 함께 움직였다면 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

with st.expander(f"🤖 AI 해설 · {target_group}", expanded=False):
    st.write(AI_NOTES.get(target_group, "이 집단의 해설은 아직 없습니다."))
st.caption(AI_SOURCE)