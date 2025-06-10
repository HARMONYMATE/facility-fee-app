import streamlit as st
import pandas as pd
from urllib.parse import quote
import unicodedata

st.set_page_config(page_title="施設利用料 自動計算ツール", layout="wide")

st.markdown("""
    <style>
    .toggle-button {
        display: inline-block;
        padding: 0.75em 1.25em;
        margin: 0.25em;
        background-color: #f0f2f6;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 500;
        transition: background-color 0.2s ease-in-out;
    }
    .toggle-button:hover {
        background-color: #e2e8f0;
    }
    .toggle-button.selected {
        background-color: #2563eb;
        color: white;
    }
    .toggle-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.25rem;
    }
    .toggle-row span.label {
        width: 6rem;
        font-weight: bold;
        display: inline-block;
    }
    .element-container:has(.dataframe) table td, .element-container:has(.dataframe) table th {
        padding: 0.2rem 0.4rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- Google Sheets 読み込み用の共通関数 ---
def load_sheet(sheet_name):
    sheet_id = "1mzdUGUeCsmmjYY99EEvrxtc4S25DkiFqMO1bnbAjW2o"
    encoded_sheet_name = quote(sheet_name, safe="")
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_sheet_name}"
    df = pd.read_csv(csv_url, header=0)
    df.columns = df.columns.map(lambda x: unicodedata.normalize('NFKC', str(x)).strip().replace('\n', '').replace('\u3000', '').replace('\r', '').replace('〜', '～'))
    if "貸館施設名" in df.columns:
        df["貸館施設名"] = df["貸館施設名"].astype(str).str.strip().str.replace('\u3000', '').str.replace('\r', '')
    if "徴収する入場料の額" in df.columns:
        df["徴収する入場料の額"] = df["徴収する入場料の額"].astype(str).str.strip().str.replace('\u3000', '').str.replace('\r', '')
    if "曜日区分" in df.columns:
        df["曜日区分"] = df["曜日区分"].astype(str).str.strip().str.replace('\u3000', '').str.replace('\r', '')
    return df

# --- 表示名とシート名のマッピング ---
利用者区分マップ = {
    "一般": "ippan",
    "一般 練習": "ippan_RH",
    "登録団体": "touroku",
    "登録団体 練習": "touroku_RH"
}

表示名 = st.radio("利用者区分", list(利用者区分マップ.keys()), horizontal=True)
利用者区分 = 利用者区分マップ[表示名]

曜日 = st.radio("曜日区分", ["平日", "休日等"], horizontal=True)
入場料 = st.radio("入場料区分（ホール利用時）", ["無料～1,000円", "1,001円～3,000円", "3,001円～5,000円", "5,001円～"], horizontal=True)

施設一覧 = [
    ("メインホール", True),
    ("小ホール", True),
    ("第１練習室", False),
    ("第２練習室", False),
    ("第３練習室", False)
]

時間区分候補 = ["午前", "午後", "夜間"]
選択時間帯 = {}

for fac, _ in 施設一覧:
    cols = st.columns([1, 1, 1, 1])
    style = "color:red; font-weight:bold;" if 選択時間帯.get(fac) else ""
    選択時間帯[fac] = []
    label_html = f"<span style='{style}'>{fac}</span>"
    cols[0].markdown(label_html, unsafe_allow_html=True)
    for i, 区分 in enumerate(時間区分候補):
        if cols[i+1].toggle(f"{区分}", key=f"{fac}_{区分}"):
            選択時間帯[fac].append(区分)

# --- データ読み込み ---
df_base = load_sheet("ippan")
df_selected = load_sheet(利用者区分)

# --- 出力表の構築 ---
time_merge = {
    frozenset(["午前"]): "午前",
    frozenset(["午後"]): "午後",
    frozenset(["夜間"]): "夜間",
    frozenset(["午前", "午後"]): "午前・午後",
    frozenset(["午後", "夜間"]): "午後・夜間",
    frozenset(["午前", "午後", "夜間"]): "全日"
}

output_rows = []
for fac, is_hall in 施設一覧:
    times = frozenset(選択時間帯[fac])
    if not times:
        output_rows.append({"施設名": fac, "利用区分": "-", "規定額": 0, "減免額": 0, "利用金額": 0})
        continue

    時間キー = time_merge.get(times, None)

    if is_hall:
        rows_base = df_base[(df_base["貸館施設名"] == fac) & (df_base["徴収する入場料の額"] == 入場料) & (df_base["曜日区分"] == 曜日)]
        rows_sel = df_selected[(df_selected["貸館施設名"] == fac) & (df_selected["徴収する入場料の額"] == 入場料) & (df_selected["曜日区分"] == 曜日)]
    else:
        rows_base = df_base[(df_base["貸館施設名"] == fac)]
        rows_sel = df_selected[(df_selected["貸館施設名"] == fac)]

    if rows_base.empty or rows_sel.empty:
        base_price = real_price = genmen = 0
    else:
        try:
            if 時間キー and 時間キー in rows_base.columns and 時間キー in rows_sel.columns:
                base_price = int(str(rows_base.iloc[0][時間キー]).replace(",", ""))
                real_price = int(str(rows_sel.iloc[0][時間キー]).replace(",", ""))
            else:
                base_price = real_price = 0
                for t in 選択時間帯[fac]:
                    if t in rows_base.columns and t in rows_sel.columns:
                        base_price += int(str(rows_base.iloc[0][t]).replace(",", ""))
                        real_price += int(str(rows_sel.iloc[0][t]).replace(",", ""))
            genmen = base_price - real_price
        except:
            base_price = real_price = genmen = 0

    利用区分表示 = 時間キー if 時間キー else ",".join(選択時間帯[fac])
    output_rows.append({
        "施設名": fac,
        "利用区分": 利用区分表示,
        "規定額": base_price,
        "減免額": genmen,
        "利用金額": real_price
    })

df_out = pd.DataFrame(output_rows)
df_out.loc["合計"] = ["合計", "",
                    df_out["規定額"].apply(lambda x: x if isinstance(x, int) else 0).sum(),
                    df_out["減免額"].apply(lambda x: x if isinstance(x, int) else 0).sum(),
                    df_out["利用金額"].apply(lambda x: x if isinstance(x, int) else 0).sum()]

st.table(df_out.reset_index(drop=True).style.hide(axis='index'))

# --- 消費税計算 ---
try:
    total = int(df_out[df_out["施設名"] == "合計"]["利用金額"])
    tax = total // 11  # 内税として10%を取り出すなら 1/11
    st.markdown(f"**消費税相当額（内税）**： ¥{tax:,}")
except:
    st.markdown("**消費税相当額（内税）**：計算できませんでした")
