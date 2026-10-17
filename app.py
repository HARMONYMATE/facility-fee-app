import unicodedata
from urllib.parse import quote

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="施設・設備利用料 計算ツール",
    page_icon="🏛️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 2.6rem;
        padding-bottom: 6rem;
    }
    .app-title {
        color: #1e293b;
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.3;
        margin: 0;
    }
    .section-title {
        color: #334155;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.25;
        margin: 0.25rem 0 0.2rem 0;
        padding-bottom: 0.15rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .facility-header {
        color: #64748b;
        font-size: 0.82rem;
        font-weight: 700;
        padding-bottom: 0.15rem;
        border-bottom: 1px solid #e2e8f0;
    }
    div[data-testid="stButton"] button {
        min-height: 2.35rem;
    }
    div[data-testid="stButton"] button p {
        font-weight: 700;
    }
    .reset-help {
        color: #64748b;
        font-size: 0.78rem;
        margin-top: -0.2rem;
    }
    div[data-testid="stRadio"] {
        margin-bottom: -0.25rem;
    }
    div[data-testid="stRadio"] > label {
        font-size: 0.85rem;
        margin-bottom: 0.05rem;
    }
    .st-key-user_category_panel div[role="radiogroup"] {
        display: grid !important;
        grid-template-columns: repeat(5, max-content);
        gap: 0.15rem 0.65rem;
        align-items: center;
    }
    .st-key-user_category_panel div[role="radiogroup"] > label {
        min-height: 2rem;
        padding: 0.2rem 0.45rem;
        border-radius: 6px;
    }
    .st-key-user_category_panel div[role="radiogroup"] > label:nth-child(-n+5) {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        font-weight: 700;
    }
    @media (max-width: 900px) {
        .st-key-user_category_panel div[role="radiogroup"] {
            grid-template-columns: repeat(2, max-content);
        }
    }
    div[data-testid="stToggle"] {
        margin-bottom: -0.25rem;
    }
    div[data-testid="stTable"] table {
        width: 100%;
    }
    div[data-testid="stTable"] th,
    div[data-testid="stTable"] td {
        padding: 0.22rem 0.45rem !important;
        font-size: 0.88rem;
    }
    div[data-testid="stAlert"] {
        border-radius: 8px;
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
    }
    .tax-line {
        color: #334155;
        font-size: 0.9rem;
        text-align: right;
        margin-top: 0.45rem;
        margin-bottom: 4rem;
        padding: 0.6rem 0.8rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 7px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


SHEET_ID = "1mzdUGUeCsmmjYY99EEvrxtc4S25DkiFqMO1bnbAjW2o"

利用者区分設定 = {
    "一般": {
        "sheet": "ippan",
        "control_room_sheet": "ippan_RH",
        "calculation": "standard",
    },
    "一般 練習": {
        "sheet": "ippan_RH",
        "control_room_sheet": None,
        "calculation": "standard",
    },
    "登録団体": {
        "sheet": "touroku",
        "control_room_sheet": "touroku_RH",
        "calculation": "standard",
    },
    "登録団体 練習": {
        "sheet": "touroku_RH",
        "control_room_sheet": None,
        "calculation": "standard",
    },
    "全免": {
        "sheet": "ippan",
        "control_room_sheet": None,
        "calculation": "full_exemption",
    },
    "30％減免": {
        "sheet": "touroku",
        "control_room_sheet": "touroku_RH",
        "calculation": "standard",
    },
    "30％減免 練習": {
        "sheet": "touroku_RH",
        "control_room_sheet": None,
        "calculation": "standard",
    },
    "50％減免": {
        "sheet": "genmen_50",
        "control_room_sheet": "genmen_65",
        "calculation": "standard",
    },
    "50％減免 練習": {
        "sheet": "genmen_65",
        "control_room_sheet": None,
        "calculation": "standard",
    },
    "音楽文化芸術以外の営利利用": {
        "sheet": "ippan",
        "control_room_sheet": None,
        "calculation": "commercial",
    },
}

ホール利用形態候補 = [
    "両方とも本番",
    "メインホールを控室",
    "小ホールを控室",
]

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
        display_time = "／".join(selected_times)

    return display_time, base_price, base_price - real_price, real_price


def apply_pricing_rule(
    calculation,
    is_hall,
    admission_fee,
    base_price,
    real_price,
):
    """全免と営利利用の個別ルールを料金表の取得後に適用する。"""
    if calculation == "full_exemption":
        return base_price, base_price, 0

    if calculation == "commercial":
        is_double_charge = (
            not is_hall or admission_fee == "無料（営利利用）"
        )
        increase = base_price if is_double_charge else 0
        return base_price, increase, base_price + increase

    return base_price, base_price - real_price, real_price


def reset_all_inputs():
    """料金条件と全施設の時間帯を初期状態に戻す。"""
    st.session_state["user_category"] = "一般"
    st.session_state["day_type"] = "平日"
    st.session_state["admission_fee"] = "無料～1,000円"
    st.session_state["hall_usage_mode"] = "両方とも本番"
    for facility, _ in 施設一覧:
        for time in 時間区分候補:
            st.session_state[f"{facility}_{time}"] = False


def toggle_all_times(facility):
    """施設名ボタンで、その施設の全時間帯を選択または解除する。"""
    all_selected = all(
        st.session_state.get(f"{facility}_{time}", False)
        for time in 時間区分候補
    )
    for time in 時間区分候補:
        st.session_state[f"{facility}_{time}"] = not all_selected


def render_facility_fee():
    """施設利用料の既存画面を表示する。"""
    st.markdown(
        '<div class="app-title">施設利用料 自動計算ツール</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("料金表")
        st.caption("料金表は10分間キャッシュされます。")
        if st.button("料金表を再読み込み", use_container_width=True):
            load_sheet.clear()
            st.rerun()

    condition_title, reset_column = st.columns([4.5, 1.3], gap="small")
    condition_title.markdown(
        '<div class="section-title">利用条件</div>',
        unsafe_allow_html=True,
    )
    reset_column.button(
        "↺ 全項目リセット",
        key="reset_all",
        on_click=reset_all_inputs,
        use_container_width=True,
    )
    with st.container(key="user_category_panel"):
        表示名 = st.radio(
            "利用者区分",
            list(利用者区分設定.keys()),
            horizontal=True,
            key="user_category",
        )
    利用者設定 = 利用者区分設定[表示名]
    利用者区分 = 利用者設定["sheet"]

    曜日 = st.radio(
        "曜日区分",
        ["平日", "休日等"],
        horizontal=True,
        key="day_type",
    )
    入場料 = st.radio(
        "入場料区分（ホール利用時）",
        [
            "無料～1,000円",
            "1,001円～3,000円",
            "3,001円～5,000円",
            "5,001円～",
            "無料（営利利用）",
        ],
        horizontal=True,
        key="admission_fee",
    )

    st.markdown(
        '<div class="section-title">利用施設・時間帯</div>',
        unsafe_allow_html=True,
    )
    facility_column_widths = [1.1, 0.75, 0.75, 0.75, 2.8]
    header_columns = st.columns(facility_column_widths, gap="small")
    for column, label in zip(
        header_columns,
        ["施設名（全選択／解除）", "午前", "午後", "夜間"],
    ):
        column.markdown(
            f'<div class="facility-header">{label}</div>',
            unsafe_allow_html=True,
        )

    選択時間帯 = {}
    for facility, _ in 施設一覧:
        any_selected_before_render = any(
            st.session_state.get(f"{facility}_{time}", False)
            for time in 時間区分候補
        )
        all_selected_before_render = all(
            st.session_state.get(f"{facility}_{time}", False)
            for time in 時間区分候補
        )

        columns = st.columns(facility_column_widths, gap="small")
        columns[0].button(
            facility,
            key=f"{facility}_all_times",
            on_click=toggle_all_times,
            args=(facility,),
            type="primary" if any_selected_before_render else "secondary",
            use_container_width=True,
        )

        選択時間帯[facility] = []
        for index, time in enumerate(時間区分候補):
            if columns[index + 1].toggle(
                time,
                key=f"{facility}_{time}",
                label_visibility="collapsed",
            ):
                選択時間帯[facility].append(time)

    両ホール選択中 = bool(選択時間帯["メインホール"]) and bool(
        選択時間帯["小ホール"]
    )
    控室選択可能 = (
        両ホール選択中
        and 利用者設定["control_room_sheet"] is not None
    )

    if 控室選択可能:
        ホール利用形態 = st.radio(
            "両ホール利用時の利用形態",
            ホール利用形態候補,
            horizontal=True,
            key="hall_usage_mode",
        )
        st.caption(
            "控室利用にしたホールは、練習料金・入場料「無料～1,000円」で計算します。"
        )
    else:
        st.session_state["hall_usage_mode"] = "両方とも本番"
        ホール利用形態 = "両方とも本番"

    控室利用施設 = {
        "メインホールを控室": "メインホール",
        "小ホールを控室": "小ホール",
    }.get(ホール利用形態)

    try:
        with st.spinner("料金表を確認しています…"):
            df_base = load_sheet("ippan")
            df_selected = (
                df_base if 利用者区分 == "ippan" else load_sheet(利用者区分)
            )
            控室料金シート名 = 利用者設定["control_room_sheet"]
            df_control_room = (
                load_sheet(控室料金シート名) if 控室利用施設 else None
            )
            validate_sheet(df_base, "ippan")
            validate_sheet(df_selected, 利用者区分)
            if df_control_room is not None:
                validate_sheet(df_control_room, 控室料金シート名)
    except Exception as exc:
        st.error(
            "料金表を読み込めませんでした。Google Sheetsの公開設定と表の内容を"
            f"確認してください。\n\n詳細：{exc}"
        )
        st.stop()

    output_rows = []
    calculation_errors = []
    surcharge_applied = False

    for facility, is_hall in 施設一覧:
        selected_times = 選択時間帯[facility]

        if not selected_times:
            output_rows.append(
                {
                    "施設名": facility,
                    "利用区分": "―",
                    "規定額": 0,
                    "調整額": 0,
                    "利用金額": 0,
                }
            )
            continue

        try:
            is_control_room = facility == 控室利用施設
            selected_fee_table = (
                df_control_room if is_control_room else df_selected
            )
            admission_fee_for_facility = 入場料
            if is_control_room or 入場料 == "無料（営利利用）":
                admission_fee_for_facility = "無料～1,000円"
            (
                display_time,
                base_price,
                adjustment,
                real_price,
            ) = calculate_prices(
                facility,
                is_hall,
                selected_times,
                admission_fee_for_facility,
                曜日,
                df_base,
                selected_fee_table,
            )
            base_price, adjustment, real_price = apply_pricing_rule(
                利用者設定["calculation"],
                is_hall,
                入場料,
                base_price,
                real_price,
            )
            is_double_charge = (
                利用者設定["calculation"] == "commercial"
                and (not is_hall or 入場料 == "無料（営利利用）")
            )
            surcharge_applied = surcharge_applied or is_double_charge
            if is_hall and 控室選択可能:
                usage_label = "控室利用" if is_control_room else "本番利用"
                display_time = f"{display_time}（{usage_label}）"
        except ValueError as exc:
            calculation_errors.append(str(exc))
            continue

        output_rows.append(
            {
                "施設名": facility,
                "利用区分": display_time,
                "規定額": base_price,
                "調整額": adjustment,
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
    adjustment_column = "増加額" if surcharge_applied else "減免額"

    total_row = {
        "施設名": "合計",
        "利用区分": "",
        "規定額": int(df_out["規定額"].sum()),
        "調整額": int(df_out["調整額"].sum()),
        "利用金額": int(df_out["利用金額"].sum()),
    }
    df_out = pd.concat([df_out, pd.DataFrame([total_row])], ignore_index=True)
    df_out = df_out.rename(columns={"調整額": adjustment_column})

    st.markdown(
        '<div class="section-title">計算結果</div>',
        unsafe_allow_html=True,
    )
    formatted_table = (
        df_out.style.hide(axis="index")
        .format(
            {
                "規定額": lambda value: f"{int(value):,}",
                adjustment_column: lambda value: f"{int(value):,}",
                "利用金額": lambda value: f"{int(value):,}",
            }
        )
        .set_properties(
            subset=["規定額", adjustment_column, "利用金額"],
            **{"text-align": "right"},
        )
    )
    if surcharge_applied:
        formatted_table = formatted_table.set_properties(
            subset=["増加額"],
            **{
                "background-color": "#fff7ed",
                "color": "#9a3412",
                "font-weight": "700",
            },
        ).set_table_styles(
            [
                {
                    "selector": "th.col3",
                    "props": [
                        ("background-color", "#ffedd5"),
                        ("color", "#9a3412"),
                        ("font-weight", "700"),
                    ],
                }
            ],
            overwrite=False,
        )
    st.table(formatted_table)

    total = int(total_row["利用金額"])
    tax = total // 11

    st.markdown(
        f'<div class="tax-line">消費税相当額（内税）：<strong>¥{tax:,}</strong></div>',
        unsafe_allow_html=True,
    )


EQUIPMENT_FEE_URL = "https://equipment-fee-prototype.agath4.chatgpt.site"


def render_equipment_fee():
    """公開中の設備ツールを表示し、設備側の更新をそのまま反映する。"""
    st.link_button("設備利用料を別画面で開く", EQUIPMENT_FEE_URL)
    if hasattr(st, "iframe"):
        st.iframe(
            EQUIPMENT_FEE_URL,
            height=1100,
            alt="設備利用料金の入力・計算・帳票印刷",
        )
    else:
        # Streamlit 1.56未満の公開環境でも、依存関係を変更せず表示する。
        from streamlit.components.v1 import iframe

        iframe(EQUIPMENT_FEE_URL, height=1100, scrolling=True)


facility_tab, equipment_tab = st.tabs(["施設利用料", "設備利用料"])

# 施設料金表の読込失敗によるst.stop()より先に、設備タブを描画する。
with equipment_tab:
    render_equipment_fee()

with facility_tab:
    render_facility_fee()
