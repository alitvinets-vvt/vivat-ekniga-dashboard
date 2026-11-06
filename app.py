# -*- coding: utf-8 -*-
"""Vivat × єКнига — інтерактивний дашборд.

Дані: зведений рейтинг УІК за 1–3 кв. 2026 (ТОП-300), звіт УІК станом на 01.10.2026,
вивантаження каталогу vivat.com.ua. Жанрова й когортна розмітка — власна.
"""
import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"
VIVAT = "#eb6834"
BLUE = "#2a78d6"
GREY = "#c9c8c0"
SEQ = ["#2a78d6", "#1baf7a", "#eb6834", "#6250d6", "#e87ba4", "#eda100", "#008300", "#e34948"]

st.set_page_config(page_title="Vivat × єКнига", page_icon="📚", layout="wide")


# ────────────────────────────── дані ──────────────────────────────
@st.cache_data
def load():
    t = pd.read_csv(DATA / "top300.csv")
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    return (
        t,
        pd.read_csv(DATA / "monthly.csv"),
        pd.read_csv(DATA / "sites.csv"),
        pd.read_csv(DATA / "shares.csv"),
        pd.read_csv(DATA / "novelty.csv"),
        meta,
    )


@st.cache_data(show_spinner="Матчимо каталог із рейтингом…")
def recount_from_catalog(file_bytes: bytes, isbns: tuple[str, ...]) -> list[str]:
    """Перерахунок наявності з нового вивантаження каталогу сайту."""
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    avail = {"В наявності", "Акція", "Передзамовлення"}
    cat: dict[str, bool] = {}
    for row in list(wb.active.iter_rows(values_only=True))[1:]:
        isbn = re.sub(r"\D", "", str(row[0] or ""))
        if len(isbn) != 13:
            continue
        ok = str(row[5] or "") in avail
        if isbn not in cat or (ok and not cat[isbn]):
            cat[isbn] = ok

    def check(raw):
        state = "немає в каталозі"
        for code in re.findall(r"\d{13}", str(raw)):
            if code in cat:
                if cat[code]:
                    return "в наявності"
                state = "у каталозі, 0 залишок"
        return state

    return [check(raw) for raw in isbns]


t, monthly, sites, shares, novelty, meta = load()

fmt = lambda v: f"{int(v):,}".replace(",", " ")


# ────────────────────────────── сайдбар ──────────────────────────────
st.sidebar.title("📚 Vivat × єКнига")
st.sidebar.caption(f"ТОП-300 за 1–3 кв. 2026 · залишки сайту на {meta['snapshot']}")

pubs = ["(усі)"] + t.groupby("publisher").qty.sum().sort_values(ascending=False).index.tolist()
pub = st.sidebar.selectbox("Видавництво", pubs)
genres = st.sidebar.multiselect("Субжанри", sorted(t.genre.unique()))
cohorts = st.sidebar.multiselect("Когорта (рік 1-го видання)", ["≤2020", "2021–22", "2023", "2024", "2025", "2026"])
availability = st.sidebar.multiselect("Наявність на сайті", sorted(t.site.unique()))
only_new = st.sidebar.checkbox("Лише новинки 2025–26")

st.sidebar.divider()
st.sidebar.subheader("Оновити дані")
upload = st.sidebar.file_uploader("Нове вивантаження каталогу (.xlsx)", type="xlsx")
if upload is not None:
    try:
        t = t.copy()
        t["site"] = recount_from_catalog(upload.getvalue(), tuple(t["isbn"].astype(str)))
        st.sidebar.success(f"Наявність перерахована з файлу {upload.name}")
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(
            "Не вдалося прочитати файл. Потрібен .xlsx з колонками "
            f"`ean_isbn` і `product_status`. ({exc})"
        )

f = t.copy()
if pub != "(усі)":
    f = f[f.publisher == pub]
if genres:
    f = f[f.genre.isin(genres)]
if cohorts:
    f = f[f.cohort.isin(cohorts)]
if availability:
    f = f[f.site.isin(availability)]
if only_new:
    f = f[f.is_new]

if f.empty:
    st.warning("Під ці фільтри нічого не підпадає — зніміть частину умов.")
    st.stop()


# ────────────────────────────── шапка ──────────────────────────────
st.title("Чому Vivat просідає у «єКнизі»")
st.caption(
    "Інтерактивний зріз даних УІК. Відсотки — частка у **штуках**, "
    "база — **ТОП-300 книжок** (67 124 шт ≈ 39% усіх продажів програми), якщо не вказано інше."
)

v = t[t.publisher == "Vivat"]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Частка Vivat, 1–3 кв. 2026", "10,04%", "-4,3 п.п. до I кв. 2025", delta_color="inverse")
k2.metric("Новинки 2025–26 у продажах Vivat", "4,2%", "у КСД — 18,1%", delta_color="off")
k3.metric("Віддача новинки 2025", "4,3 шт", "у КСД — 26,0 шт", delta_color="off")
k4.metric(
    "Сайт закриває попит ТОП-300",
    f"{t[t.site == 'в наявності'].qty.sum() / t.qty.sum():.0%}",
    f"{meta['catalog_available']} доступних SKU із {fmt(meta['catalog_skus'])}",
    delta_color="off",
)

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Огляд", "Новинки vs бекліст", "Жанри", "Канали і залишки", "Дані"]
)


# ────────────────────────────── огляд ──────────────────────────────
with tab1:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("Динаміка програми по місяцях")
        m = monthly.melt("month", var_name="рік", value_name="книжок").dropna()
        m["рік"] = m["рік"].str.replace("y", "")
        fig = px.line(m, x="month", y="книжок", color="рік", markers=True,
                      color_discrete_sequence=[BLUE, VIVAT])
        fig.update_layout(height=340, margin=dict(t=10, b=0, l=0, r=0), xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Січень 2025 — стартовий сплеск (128,6 тис.). У порівнянних періодах: "
            "січень–вересень −52%, червень–вересень −18%. Програма вийшла на плато 16–22 тис./міс."
        )
    with c2:
        st.subheader("Частка видавництв у штуках")
        s = shares.melt("publisher", var_name="період", value_name="частка").dropna()
        s["період"] = s["період"].map(
            {"q1_2025": "I кв. 2025", "y2025": "2025 рік", "q1_3_2026": "1–3 кв. 2026"}
        )
        fig = px.line(s, x="період", y="частка", color="publisher", markers=True,
                      color_discrete_sequence=SEQ)
        fig.update_layout(height=340, margin=dict(t=10, b=0, l=0, r=0),
                          xaxis_title=None, yaxis_title="% штук програми")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("ТОП-300 за видавцями")
    pp = t.groupby("publisher").qty.sum().sort_values(ascending=False)
    top8 = pp.head(8)
    pie = pd.concat([top8, pd.Series({f"Решта {len(pp) - 8} видавців": pp.iloc[8:].sum()})])
    fig = px.pie(values=pie.values, names=pie.index, hole=0.45,
                 color_discrete_sequence=SEQ + [GREY])
    fig.update_traces(textinfo="label+percent", textposition="inside")
    fig.update_layout(height=430, margin=dict(t=10, b=10, l=0, r=0), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)


# ────────────────────────────── когорти ──────────────────────────────
with tab2:
    st.subheader("Структура продажів за роком першого видання")
    st.caption("Головний механізм падіння: Vivat живе на беклісті, конкуренти — на свіжих хітах.")
    order = ["≤2020", "2021–22", "2023", "2024", "2025", "2026"]
    sel = ["Ринок (ТОП-300)", "КСД", "BookChef", "Vivat", "РМ"]
    rows = []
    for name in sel:
        src = t if name.startswith("Ринок") else t[t.publisher == name]
        tot = src.qty.sum()
        for c in order:
            rows.append({"гравець": name, "когорта": c,
                         "частка": src[src.cohort == c].qty.sum() / tot * 100})
    fig = px.bar(pd.DataFrame(rows), x="частка", y="гравець", color="когорта", orientation="h",
                 category_orders={"когорта": order, "гравець": sel[::-1]},
                 color_discrete_sequence=["#86b6ef", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
    fig.update_layout(height=330, margin=dict(t=10, b=0, l=0, r=0),
                      xaxis_title="% власних штук", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Віддача однієї новинки 2025")
        fig = px.bar(novelty.sort_values("units_per_title"), x="units_per_title", y="publisher",
                     orientation="h", text="units_per_title",
                     color=novelty.sort_values("units_per_title").publisher.eq("Vivat"),
                     color_discrete_map={True: VIVAT, False: BLUE})
        fig.update_layout(height=330, showlegend=False, margin=dict(t=10, b=0, l=0, r=0),
                          xaxis_title="шт на назву", yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Vivat видав у програмі 155 новинок 2025 — майже як КСД (169). Різниця у віддачі назви.")
    with c2:
        st.subheader("Новинки 2025–26 у ТОП-300")
        nf = t[t.is_new].groupby("publisher").qty.sum().sort_values(ascending=False).head(8)
        fig = px.bar(x=nf.values, y=nf.index, orientation="h", text=nf.values,
                     color=pd.Series(nf.index).eq("Vivat").values,
                     color_discrete_map={True: VIVAT, False: BLUE})
        fig.update_layout(height=330, showlegend=False, margin=dict(t=10, b=0, l=0, r=0),
                          xaxis_title="шт", yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)


# ────────────────────────────── жанри ──────────────────────────────
with tab3:
    g = t.groupby("genre").qty.agg(["size", "sum"]).sort_values("sum", ascending=False)
    g["частка"] = (g["sum"] / t.qty.sum() * 100).round(1)
    gv = t[t.publisher == "Vivat"].groupby("genre").qty.sum()
    g["Vivat, шт"] = g.index.map(gv).fillna(0).astype(int)
    g["частка Vivat"] = (g["Vivat, шт"] / g["sum"] * 100).round(1)

    c1, c2 = st.columns([2, 3])
    with c1:
        st.subheader("Структура попиту")
        top8 = g.head(8)["sum"]
        pie = pd.concat([top8, pd.Series({f"Решта {len(g) - 8}": g["sum"].iloc[8:].sum()})])
        fig = px.pie(values=pie.values, names=pie.index, hole=0.45,
                     color_discrete_sequence=SEQ + [GREY])
        fig.update_traces(textinfo="percent", textposition="inside")
        fig.update_layout(height=420, margin=dict(t=10, b=0, l=0, r=0),
                          legend=dict(font=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Місце Vivat у кожному субжанрі")
        d = g.reset_index().sort_values("sum")
        fig = go.Figure()
        fig.add_bar(y=d.genre, x=d["Vivat, шт"], orientation="h", name="Vivat", marker_color=VIVAT)
        fig.add_bar(y=d.genre, x=d["sum"] - d["Vivat, шт"], orientation="h",
                    name="решта ринку", marker_color=GREY)
        fig.update_layout(barmode="stack", height=420, margin=dict(t=10, b=0, l=0, r=0),
                          xaxis_title="шт у ТОП-300", legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        g.rename(columns={"size": "назв", "sum": "шт"})[
            ["назв", "шт", "частка", "Vivat, шт", "частка Vivat"]
        ],
        use_container_width=True,
    )

    st.subheader("Топ-5 тайтлів обраних субжанрів")
    pick = st.multiselect("Субжанр", g.index.tolist(), default=g.index[:3].tolist())
    cols = st.columns(min(3, max(1, len(pick))))
    for i, gg in enumerate(pick):
        with cols[i % len(cols)]:
            st.markdown(f"**{gg}** · {fmt(g.loc[gg, 'sum'])} шт")
            for _, r in t[t.genre == gg].nlargest(5, "qty").iterrows():
                mark = "🟠 " if r.publisher == "Vivat" else ""
                st.markdown(
                    f"{mark}**{fmt(r.qty)}** · {r.title[:46]}  \n<small>{r.publisher}</small>",
                    unsafe_allow_html=True,
                )


# ────────────────────────────── канали ──────────────────────────────
with tab4:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Частка сайтів в онлайн-грошах")
        s = sites.melt("site", var_name="рік", value_name="частка")
        s["рік"] = s["рік"].map({"share2025": "2025", "share2026": "2026 (9 міс.)"})
        fig = px.bar(s, x="частка", y="site", color="рік", orientation="h", barmode="group",
                     color_discrete_sequence=[BLUE, VIVAT])
        fig.update_layout(height=380, margin=dict(t=10, b=0, l=0, r=0),
                          yaxis_title=None, xaxis_title="% онлайн-оплат")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("MEGOGO — єдиний, хто виріс абсолютно: бандл Megopak під ваучер 998 грн.")
    with c2:
        st.subheader("Чи є хіти програми на сайті")
        groups = {
            "Увесь ТОП-300": t,
            "ТОП-50": t.nsmallest(50, "rank"),
            "Новинки 2025–26": t[t.is_new],
            "Чужі видавці": t[t.publisher != "Vivat"],
            "Власні Vivat": t[t.publisher == "Vivat"],
        }
        rows = []
        for name, d in groups.items():
            for s_ in ["в наявності", "у каталозі, 0 залишок", "немає в каталозі"]:
                rows.append({"група": name, "стан": s_,
                             "частка": d[d.site == s_].qty.sum() / d.qty.sum() * 100})
        fig = px.bar(pd.DataFrame(rows), x="частка", y="група", color="стан", orientation="h",
                     category_orders={"група": list(groups)[::-1]},
                     color_discrete_map={"в наявності": BLUE, "у каталозі, 0 залишок": "#eda100",
                                         "немає в каталозі": GREY})
        fig.update_layout(height=380, margin=dict(t=10, b=0, l=0, r=0),
                          xaxis_title="% попиту групи", yaxis_title=None,
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Знімок {meta['snapshot']}. Наявність = «В наявності» + «Акція» + «Передзамовлення».")

    st.subheader("Що докупити або додрукувати")
    st.caption("Хіти ТОП-300, яких сьогодні не можна купити на сайті — за спаданням попиту програми.")
    gap = t[t.site != "в наявності"].copy()
    gap["дія"] = gap.publisher.eq("Vivat").map({True: "додрукувати", False: "закупити"})
    st.dataframe(
        gap[["rank", "author", "title", "publisher", "genre", "qty", "site", "дія"]]
        .rename(columns={"rank": "№", "author": "автор", "title": "назва",
                         "publisher": "видавець", "genre": "субжанр", "qty": "попит, шт",
                         "site": "стан на сайті"})
        .sort_values("попит, шт", ascending=False),
        use_container_width=True, height=400,
    )
    st.download_button("⬇️ Завантажити перелік (CSV)",
                       gap.to_csv(index=False).encode("utf-8-sig"),
                       "vivat-ekniga-shopping-list.csv", "text/csv")


# ────────────────────────────── дані ──────────────────────────────
with tab5:
    st.subheader("ТОП-300 з фільтрами сайдбара")
    st.caption(f"Відібрано {len(f)} назв · {fmt(f.qty.sum())} шт "
               f"({f.qty.sum() / t.qty.sum():.1%} ТОП-300)")
    st.dataframe(
        f[["rank", "author", "title", "publisher", "genre", "years", "cohort", "qty", "site", "stock"]]
        .rename(columns={"rank": "№", "author": "автор", "title": "назва", "publisher": "видавець",
                         "genre": "субжанр", "years": "роки видань", "cohort": "когорта",
                         "qty": "шт", "site": "стан на сайті", "stock": "залишок"}),
        use_container_width=True, height=520,
    )
    st.download_button("⬇️ Завантажити вибірку (CSV)",
                       f.to_csv(index=False).encode("utf-8-sig"),
                       "vivat-ekniga-selection.csv", "text/csv")

    with st.expander("Джерела і застереження"):
        st.markdown(
            """
- **Зведений рейтинг УІК за 1–3 кв. 2026** — повний і безперервний лише до 300-ї позиції (поріг 80 шт),
  тому всі жанрові й когортні розрізи рахуються на ТОП-300 (67 124 шт ≈ 39% програми).
- **Звіт УІК станом на 01.10.2026** — суми, канали, демографія, місячна динаміка.
- **Вивантаження каталогу vivat.com.ua** на 06.11.2026 — знімок одного дня;
  «нуль залишку» може означати і «розпродано», тож покриття оцінене знизу.
- Жанрова розмітка і когорти за роком першого видання — власні розрахунки, не дані УІК.
- ТОП-300 покриває гравців нерівномірно: у КСД/BookChef туди потрапляє 60–63% їхніх штук,
  у РМ — 71%, у Vivat — лише 46%.
            """
        )

st.divider()
st.caption("Підготовлено для внутрішнього стратегування Vivat · листопад 2026 · "
           "дані УІК + власні розрахунки")
