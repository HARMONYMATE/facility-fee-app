import unicodedata
from urllib.parse import quote

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="施設利用料 自動計算ツール",
    page_icon="🏛️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1120px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    .app-caption {
        color: #64748b;
        margin-top: -0.5rem;
        margin-bottom: 1.5rem;
    }
    .facility-header {
        color: #64748b;
        font-size: 0.9rem;
        font-weight: 700;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .facility-name {
        color: #31333f;
        font-weight: 700;
        padding-top: 0.45rem;
    }
    .facility-name.selected {
        color: #2563eb;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #e2e8f0;
        border-radius: 12px;
    }
    div[data-testid="stTable"] table {
        width: 100%;
    }
    div[data-testid="stTable"] th,
    div[data-testid="stTable"] td {
        padding: 0.45rem 0.65rem !important;
    }
    div[data-testid="stAlert"] {
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


SHEET_ID = "1mzdUGUeCsmmjYY99EEvrxtc4S25DkiFqMO1bnbAjW2o"

利用者区分マップ = {
    "一般": "ippan",
    "一般 練習": "ippan_RH",
    "登録団体": "touroku",
    "登録団体 練習": "touroku_RH",
}

施設一覧 = [
    ("メインホール", True),
    ("小ホール", True),
    ("第１練習室", False),
    ("第２練習室", False),
    ("第３練習室", False),
]

時間区分候補 = ["午前", "午後", "夜間"]

時間区分マップ = {
    frozenset(["午前"]): "午前",
    frozenset(["午後"]): "午後",
    frozenset(["夜間"]): "夜間",
    frozenset(["午前", "午後"]): "午前・午後",
    frozenset(["午後", "夜間"]): "午後・夜間",
    frozenset(["午前", "午後", "夜間"]): "全日",
}


def normalize_text(value):
    """料金表の見出しや文字列を比較しやすい形にそろえる。"""
    return (
        unicodedata.normalize("NFKC", str(value))
        .strip()
        .replace("\n", "")
        .replace("\r", "")
        .replace("\u3000", "")
        .replace("〜", "～")
        .replace("~", "～")
    )


@st.cache_data(ttl=600, show_spinner=False)
def load_sheet(sheet_name):
    """Google Sheetsを読み込み、10分間キャッシュする。"""
    encoded_sheet_name = quote(sheet_name, safe="")
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={encoded_sheet_name}"
    )

    df = pd.read_csv(csv_url, header=0)
    df.columns = [normalize_text(column) for column in df.columns]

    for column in ["貸館施設名", "徴収する入場料の額", "曜日区分"]:
        if column in df.columns:
            df[column] = df[column].map(normalize_text)

    return df


def validate_sheet(df, sheet_name):
    """計算に必要な列がそろっているか確認する。"""
    required_columns = {
        "貸館施設名",
        "午前",
        "午後",
        "夜間",
        "午前・午後",
        "午後・夜間",
        "全日",
    }
    hall_columns = {"徴収する入場料の額", "曜日区分"}
    missing = sorted((required_columns | hall_columns) - set(df.columns))

    if missing:
        raise ValueError(
            f"料金表「{sheet_name}」に必要な列がありません：{', '.join(missing)}"
        )


def parse_price(value, context):
    """料金セルを整数に変換し、異常値は明示的なエラーにする。"""
    if pd.isna(value):
        raise ValueError(f"{context}の料金が空欄です。")

    normalized = (
        unicodedata.normalize("NFKC", str(value))
        .replace(",", "")
        .replace("円", "")
        .strip()
    )

    try:
        return int(float(normalized))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{context}の料金「{value}」を数値として読み取れません。"
        ) from exc


def find_price_rows(df, facility, is_hall, admission_fee, day_type):
    """選択条件に一致する料金表の行を取得する。"""
    # 料金表側はNFKC正規化済みなので、選択値側も同じ形にそろえて比較する。
    # 例：「第２練習室」→「第2練習室」
    normalized_facility = normalize_text(facility)
    rows = df[df["貸館施設名"] == normalized_facility]

    if is_hall:
        rows = rows[
            (
                rows["徴収する入場料の額"]
                == normalize_text(admission_fee)
            )
            & (rows["曜日区分"] == normalize_text(day_type))
        ]

    return rows


def calculate_prices(
    facility,
    is_hall,
    selected_times,
    admission_fee,
    day_type,
    df_base,
    df_selected,
):
    """規定額と実際の利用金額を各料金表から取得する。"""
    base_rows = find_price_rows(
        df_base, facility, is_hall, admission_fee, day_type
    )
    selected_rows = find_price_rows(
        df_selected, facility, is_hall, admission_fee, day_type
    )

    conditions = f"{facility}／{day_type}"
    if is_hall:
        conditions += f"／{admission_fee}"

    if base_rows.empty:
        raise ValueError(f"一般料金表に該当データがありません：{conditions}")
    if selected_rows.empty:
        raise ValueError(f"選択した料金表に該当データがありません：{conditions}")

    if len(base_rows) > 1 or len(selected_rows) > 1:
        raise ValueError(f"料金表に該当データが複数あります：{conditions}")

    merged_time = 時間区分マップ.get(frozenset(selected_times))

    if merged_time:
        base_price = parse_price(
            base_rows.iloc[0][merged_time],
            f"{conditions}／{merged_time}／規定額",
        )
        real_price = parse_price(
            selected_rows.iloc[0][merged_time],
            f"{conditions}／{merged_time}／利用金額",
        )
        display_time = merged_time
    else:
        # 「午前＋夜間」のように連続しない選択は各時間帯を合算する。
        base_price = 0
        real_price = 0
        for selected_time in selected_times:
            base_price += parse_price(
                base_rows.iloc[0][selected_time],
                f"{conditions}／{selected_time}／規定額",
            )
            real_price += parse_price(
                selected_rows.iloc[0][selected_time],
                f"{conditions}／{selected_time}／利用金額",
            )
        display_time = "・".join(selected_times)

    return display_time, base_price, base_price - real_price, real_price


st.title("施設利用料 自動計算ツール")
st.markdown(
    '<p class="app-caption">利用条件と時間帯を選択すると、料金を自動計算します。</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("料金表")
    st.caption("料金表は10分間キャッシュされます。")
    if st.button("料金表を再読み込み", use_container_width=True):
        load_sheet.clear()
        st.rerun()

with st.container(border=True):
    st.subheader("1．利用条件")
    表示名 = st.radio(
        "利用者区分",
        list(利用者区分マップ.keys()),
        horizontal=True,
    )
    利用者区分 = 利用者区分マップ[表示名]

    曜日 = st.radio(
        "曜日区分",
        ["平日", "休日等"],
        horizontal=True,
    )
    入場料 = st.radio(
        "入場料区分（ホール利用時）",
        [
            "無料～1,000円",
            "1,001円～3,000円",
            "3,001円～5,000円",
            "5,001円～",
        ],
        horizontal=True,
    )

with st.container(border=True):
    st.subheader("2．利用施設・時間帯")

    header_columns = st.columns([1.6, 1, 1, 1], gap="small")
    for column, label in zip(
        header_columns,
        ["施設名", "午前", "午後", "夜間"],
    ):
        column.markdown(
            f'<div class="facility-header">{label}</div>',
            unsafe_allow_html=True,
        )

    選択時間帯 = {}
    for facility, _ in 施設一覧:
        selected_before_render = any(
            st.session_state.get(f"{facility}_{time}", False)
            for time in 時間区分候補
        )
        selected_class = " selected" if selected_before_render else ""

        columns = st.columns([1.6, 1, 1, 1], gap="small")
        columns[0].markdown(
            f'<div class="facility-name{selected_class}">{facility}</div>',
            unsafe_allow_html=True,
        )

        選択時間帯[facility] = []
        for index, time in enumerate(時間区分候補):
            if columns[index + 1].toggle(
                time,
                key=f"{facility}_{time}",
                label_visibility="collapsed",
            ):
                選択時間帯[facility].append(time)

try:
    with st.spinner("料金表を確認しています…"):
        df_base = load_sheet("ippan")
        df_selected = (
            df_base if 利用者区分 == "ippan" else load_sheet(利用者区分)
        )
        validate_sheet(df_base, "ippan")
        validate_sheet(df_selected, 利用者区分)
except Exception as exc:
    st.error(
        "料金表を読み込めませんでした。Google Sheetsの公開設定と表の内容を"
        f"確認してください。\n\n詳細：{exc}"
    )
    st.stop()

output_rows = []
calculation_errors = []

for facility, is_hall in 施設一覧:
    selected_times = 選択時間帯[facility]

    if not selected_times:
        output_rows.append(
            {
                "施設名": facility,
                "利用区分": "―",
                "規定額": 0,
                "減免額": 0,
                "利用金額": 0,
            }
        )
        continue

    try:
        (
            display_time,
            base_price,
            reduction,
            real_price,
        ) = calculate_prices(
            facility,
            is_hall,
            selected_times,
            入場料,
            曜日,
            df_base,
            df_selected,
        )
    except ValueError as exc:
        calculation_errors.append(str(exc))
        continue

    output_rows.append(
        {
            "施設名": facility,
            "利用区分": display_time,
            "規定額": base_price,
            "減免額": reduction,
            "利用金額": real_price,
        }
    )

if calculation_errors:
    st.error(
        "料金を確定できない項目があります。料金表を確認してください。\n\n"
        + "\n\n".join(f"・{message}" for message in calculation_errors)
    )
    st.stop()

df_out = pd.DataFrame(output_rows)

total_row = {
    "施設名": "合計",
    "利用区分": "",
    "規定額": int(df_out["規定額"].sum()),
    "減免額": int(df_out["減免額"].sum()),
    "利用金額": int(df_out["利用金額"].sum()),
}
df_out = pd.concat([df_out, pd.DataFrame([total_row])], ignore_index=True)

st.subheader("3．計算結果")
formatted_table = (
    df_out.style.hide(axis="index")
    .format(
        {
            "規定額": lambda value: f"{int(value):,}",
            "減免額": lambda value: f"{int(value):,}",
            "利用金額": lambda value: f"{int(value):,}",
        }
    )
    .set_properties(
        subset=["規定額", "減免額", "利用金額"],
        **{"text-align": "right"},
    )
)
st.table(formatted_table)

total = int(total_row["利用金額"])
tax = total // 11

result_columns = st.columns([1, 1, 1])
result_columns[0].metric("規定額合計", f"¥{total_row['規定額']:,}")
result_columns[1].metric("減免額合計", f"¥{total_row['減免額']:,}")
result_columns[2].metric("利用金額合計", f"¥{total:,}")

st.info(f"消費税相当額（内税）：¥{tax:,}")
