from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

from coleta_cvm import atualizar_base_diaria_cvm

API_BASE_URL = "http://127.0.0.1:8000"
CSV_PATH = Path("dados_pl_cvm.csv")
BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

FUNDOS_CONFIG: dict[str, dict[str, object]] = {
    "29242441000181": {
        "nome": "ABSOLUTE ICATU I PREV FIC DE FIF MULTIMERCADO",
        "gestora": "ABSOLUTE GESTAO DE INVESTIMENTOS LTDA",
        "pfee_pct": 20.0,
        "cdi_pct": 100.0,
    },
    "26179685000179": {
        "nome": "GARDE D'ARTAGNAN ADVISORY FIC FIM",
        "gestora": "GARDE ASSET MANAGEMENT GESTAO DE RECURSOS LTDA",
        "pfee_pct": 20.0,
        "cdi_pct": 100.0,
    },
}

CNPJS_SUPORTADOS: list[str] = list(FUNDOS_CONFIG.keys())
CNPJ_ALVO = CNPJS_SUPORTADOS[0]
NOME_FUNDO_PADRAO = str(FUNDOS_CONFIG[CNPJ_ALVO]["nome"])
GESTORA_PADRAO = str(FUNDOS_CONFIG[CNPJ_ALVO]["gestora"])
PFEE_PERCENTUAL_PADRAO = float(FUNDOS_CONFIG[CNPJ_ALVO]["pfee_pct"])
PFEE_CDI_PCT_PADRAO = float(FUNDOS_CONFIG[CNPJ_ALVO]["cdi_pct"])

st.set_page_config(
    page_title="CVM Funds — Taxa de Performance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Estilo visual ---
st.markdown(
    '<style>'
    '.stApp { background-color: #ffffff; color: #1f2937; font-family: "Inter", "Segoe UI", sans-serif; }'
    'section[data-testid="stSidebar"] { background-color: #141518; color: #e5e7eb; }'
    'section[data-testid="stSidebar"] > div, section[data-testid="stSidebar"] label, '
    'section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] h1, '
    'section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 { color: #e5e7eb; }'
    'section[data-testid="stSidebar"] div[data-testid="stTextInput"] input, '
    'section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:focus, '
    'section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:active {'
    'background-color: #1f2127 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; '
    'border-color: #2e313a !important; border-radius: 10px; opacity: 1 !important; }'
    'section[data-testid="stSidebar"] div[data-testid="stDateInput"] input {'
    'background-color: #1f2127 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; '
    'border-color: #2e313a !important; border-radius: 10px; }'
    'section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-testid="InputInstructions"], '
    'section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-testid="InputInstructions"] * {'
    'color: #9ca3af !important; -webkit-text-fill-color: #9ca3af !important; opacity: 1 !important; }'
    'section[data-testid="stSidebar"] div[data-testid="stSelectbox"] [data-baseweb="select"] > div {'
    'background-color: #f0f2f6 !important; border-color: #d1d5db !important; border-radius: 10px; }'
    'section[data-testid="stSidebar"] div[data-testid="stSelectbox"] [data-baseweb="select"] div, '
    'section[data-testid="stSidebar"] div[data-testid="stSelectbox"] [data-baseweb="select"] span, '
    'section[data-testid="stSidebar"] div[data-testid="stSelectbox"] [data-baseweb="select"] input {'
    'color: #000000 !important; -webkit-text-fill-color: #000000 !important; opacity: 1 !important; }'
    'section[data-testid="stSidebar"] .stButton > button {'
    'border-radius: 8px; font-weight: 600; }'
    '.hist-title { font-size: 1.45rem; font-weight: 700; color: #111827; margin-bottom: 0.15rem; }'
    '.hist-subtitle { font-size: 0.85rem; color: #6b7280; margin-bottom: 0.85rem; }'
    '.rule-banner { background-color: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px; '
    'padding: 0.7rem 1rem; font-size: 0.83rem; color: #374151; margin-bottom: 1rem; }'
    '.kpi-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.75rem; margin-bottom: 1.15rem; }'
    '@media (max-width: 1200px) { .kpi-row { grid-template-columns: repeat(3, minmax(0, 1fr)); } }'
    '@media (max-width: 700px) { .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); } }'
    '.kpi-box { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 0.85rem 1rem; min-height: 88px; display: flex; flex-direction: column; justify-content: space-between; }'
    '.kpi-title { font-size: 0.8rem; font-weight: 500; color: #4b5563; }'
    '.kpi-val { font-size: 1.05rem; font-weight: 700; color: #111827; margin: 0.25rem 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'
    '.kpi-sub { font-size: 0.75rem; color: #6b7280; }'
    '.cnpj-modal-code { display: inline-block; color: #374151; font-family: monospace; font-size: 0.9rem; margin-top: 0.4rem; }'
    '#vg-tooltip-element.vg-tooltip { background-color: #ffffff !important; color: #111827 !important; border: 1px solid #e5e7eb !important; border-radius: 12px !important; box-shadow: 0 10px 25px -5px rgba(17, 24, 39, 0.12), 0 4px 10px -2px rgba(17, 24, 39, 0.06) !important; padding: 10px 14px !important; font-family: "Inter", "Segoe UI", sans-serif !important; font-size: 0.84rem !important; line-height: 1.45 !important; }'
    '#vg-tooltip-element.vg-tooltip table { width: 100%; border-collapse: collapse; }'
    '#vg-tooltip-element.vg-tooltip tr:first-child td.key { font-weight: 700 !important; color: #4b5563 !important; font-size: 0.86rem !important; padding-bottom: 6px !important; border-bottom: 1px solid #f1f3f5 !important; }'
    '#vg-tooltip-element.vg-tooltip tr:first-child td.value { font-weight: 700 !important; color: #111827 !important; font-size: 0.86rem !important; padding-bottom: 6px !important; border-bottom: 1px solid #f1f3f5 !important; }'
    '#vg-tooltip-element.vg-tooltip tr:not(:first-child) td { padding-top: 4px !important; }'
    '#vg-tooltip-element.vg-tooltip td.key { color: #6b7280 !important; font-weight: 500 !important; padding-right: 14px !important; }'
    '#vg-tooltip-element.vg-tooltip td.value { color: #111827 !important; font-weight: 700 !important; text-align: right !important; }'
    '[data-testid="stDeployButton"] { display: none !important; }'
    '</style>',
    unsafe_allow_html=True,
)


def normalizar_cnpj(valor: object) -> str:
    if pd.isna(valor):
        return ""
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def formatar_cnpj(cnpj: str) -> str:
    digitos = "".join(ch for ch in str(cnpj) if ch.isdigit()).zfill(14)
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def validar_cnpj(valor: str) -> tuple[bool, str]:
    """Valida formato e dígitos verificadores do CNPJ."""
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    if len(digitos) != 14:
        return False, "Nenhum registro encontrado para o CNPJ"
    if digitos == digitos[0] * 14:
        return False, "Nenhum registro encontrado para o CNPJ"

    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_1 = sum(int(digitos[i]) * pesos_1[i] for i in range(12))
    resto_1 = soma_1 % 11
    dv_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int(digitos[12]) != dv_1:
        return False, "Nenhum registro encontrado para o CNPJ"

    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_2 = sum(int(digitos[i]) * pesos_2[i] for i in range(13))
    resto_2 = soma_2 % 11
    dv_2 = 0 if resto_2 < 2 else 11 - resto_2
    if int(digitos[13]) != dv_2:
        return False, "Nenhum registro encontrado para o CNPJ"

    return True, ""


def formatar_moeda(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_cota(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    return f"{valor:,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_pct(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    sinal = "+" if valor > 0 else ""
    return f"{sinal}{valor:.2f}%".replace(".", ",")


def _semestre_civil_label(dt: pd.Timestamp) -> str:
    sem = 1 if dt.month <= 6 else 2
    return f"{dt.year}.{sem}S"


def _semestre_chave_filtro(dt: pd.Timestamp) -> str:
    sem = 1 if dt.month <= 6 else 2
    return f"{dt.year}.{sem}"


def _gerar_opcoes_semestres(df_dados: pd.DataFrame, dt_ini_padrao: date = date(2018, 10, 1)) -> list[str]:
    """Gera lista ordenada de semestres no formato YYYY.1 / YYYY.2."""
    semestres: set[str] = set()
    fim_ref = datetime.now().date()
    if not df_dados.empty and "DT_COMPTC" in df_dados.columns:
        datas = pd.to_datetime(df_dados["DT_COMPTC"], errors="coerce").dropna()
        if not datas.empty:
            for d in datas:
                semestres.add(_semestre_chave_filtro(pd.Timestamp(d)))
            fim_ref = max(fim_ref, datas.max().date())

    ano, sem = dt_ini_padrao.year, (1 if dt_ini_padrao.month <= 6 else 2)
    ano_fim, sem_fim = fim_ref.year, (1 if fim_ref.month <= 6 else 2)
    while (ano, sem) <= (ano_fim, sem_fim):
        semestres.add(f"{ano}.{sem}")
        if sem == 1:
            sem = 2
        else:
            ano += 1
            sem = 1

    def _ordem(s: str) -> tuple[int, int]:
        partes = s.split(".")
        return (int(partes[0]), int(partes[1]))

    return sorted(semestres, key=_ordem)


def _limites_semestre(sem_label: str) -> tuple[date, date]:
    ano_str, sem_str = sem_label.split(".")
    ano = int(ano_str)
    sem = int(sem_str)
    if sem == 1:
        return date(ano, 1, 1), date(ano, 6, 30)
    return date(ano, 7, 1), date(ano, 12, 31)


def calcular_pfee_serie(
    df_serie: pd.DataFrame,
    df_cdi: pd.DataFrame,
    perc_pfee: float = PFEE_PERCENTUAL_PADRAO,
    perc_cdi: float = PFEE_CDI_PCT_PADRAO,
    respeitar_benchmark_negativo: bool = True,
) -> pd.DataFrame:
    """
    Apura a taxa de performance diária por semestre civil conforme o Art. 14 e o Anexo -
    Metodologia da Taxa de Performance do regulamento do fundo:
    - 20,00% sobre a valorização da cota que, em cada semestre civil, exceder 100% do CDI acumulado.
    - Apurada e provisionada por dia útil até o último dia útil de cada semestre civil;
      ao iniciar um novo semestre civil, a cota base do novo semestre parte da última cota do semestre anterior.
    - Regra de Benchmark Negativo (Anexo, item 2): se a cota base valorizada pelo índice de referência
      for inferior à cota base ("Benchmark Negativo"), a pfee a ser provisionada e paga calcula-se
      sobre (cota_bruta - cota_base_valorizada_cdi) sem observância de limitação.
    """
    base = (
        df_serie[["DT_COMPTC", "VL_QUOTA", "VL_PATRIM_LIQ"]]
        .dropna(subset=["DT_COMPTC", "VL_QUOTA"])
        .sort_values("DT_COMPTC")
        .drop_duplicates(subset=["DT_COMPTC"], keep="last")
        .reset_index(drop=True)
    )
    if base.empty:
        return pd.DataFrame()

    if not df_cdi.empty:
        df_m = pd.merge(base, df_cdi, on="DT_COMPTC", how="left").sort_values("DT_COMPTC").reset_index(drop=True)
        df_m["CDI_DIA_PCT"] = df_m["VALOR"].fillna(0.0)
    else:
        df_m = base.copy()
        df_m["CDI_DIA_PCT"] = 0.0

    df_m["Semestre"] = df_m["DT_COMPTC"].apply(_semestre_civil_label)
    taxa_pfee = perc_pfee / 100.0
    fator_cdi_mult = perc_cdi / 100.0

    # Mapeia a ultima cota de cada semestre para definir a cota base do semestre seguinte
    ultima_cota_por_sem: dict[str, float] = {}
    for sem_lbl, grp in df_m.groupby("Semestre", sort=False):
        ultima_cota_por_sem[sem_lbl] = float(grp["VL_QUOTA"].iloc[-1])

    # Cota do primeiro dia de 01/2021 (ou primeiro pregao de 01/2021) para o semestre 2021.1S
    jan_2021 = df_m[
        (df_m["DT_COMPTC"].dt.year == 2021) & (df_m["DT_COMPTC"].dt.month == 1)
    ].sort_values("DT_COMPTC")
    cota_base_2021_1 = float(jan_2021["VL_QUOTA"].iloc[0]) if not jan_2021.empty else None

    def _semestre_anterior_label(sem_lbl: str) -> str:
        base_str = sem_lbl.replace("S", "")
        ano_s, sem_s = base_str.split(".")
        ano_i, sem_i = int(ano_s), int(sem_s)
        if sem_i == 2:
            return f"{ano_i}.1S"
        return f"{ano_i - 1}.2S"

    def _resolver_cota_base_semestre(sem_lbl: str, cota_fallback: float) -> float:
        if sem_lbl == "2021.1S" and cota_base_2021_1 is not None:
            return cota_base_2021_1
        sem_ant = _semestre_anterior_label(sem_lbl)
        if sem_ant in ultima_cota_por_sem:
            return ultima_cota_por_sem[sem_ant]
        return cota_fallback

    linhas = []
    semestre_atual = df_m["Semestre"].iloc[0]
    cota_base_sem = _resolver_cota_base_semestre(semestre_atual, float(df_m["VL_QUOTA"].iloc[0]))
    cota_base_cdi_acum = cota_base_sem
    pfee_unit_semestre_anterior = 0.0

    for idx, row in df_m.iterrows():
        sem = row["Semestre"]
        cota_atual = float(row["VL_QUOTA"])
        pl_atual = float(row["VL_PATRIM_LIQ"]) if pd.notna(row["VL_PATRIM_LIQ"]) else 0.0
        cdi_dia_fator = 1.0 + ((float(row["CDI_DIA_PCT"]) / 100.0) * fator_cdi_mult)

        if sem != semestre_atual:
            cota_base_sem = _resolver_cota_base_semestre(sem, cota_atual)
            cota_base_cdi_acum = cota_base_sem * cdi_dia_fator
            pfee_unit_semestre_anterior = 0.0
            semestre_atual = sem
        else:
            if idx == 0:
                cota_base_cdi_acum = cota_base_sem * cdi_dia_fator
            else:
                cota_base_cdi_acum = cota_base_cdi_acum * cdi_dia_fator

        benchmark_negativo = cota_base_cdi_acum < cota_base_sem

        if respeitar_benchmark_negativo and benchmark_negativo:
            excesso_cota = cota_atual - cota_base_cdi_acum
        else:
            excesso_cota = cota_atual - cota_base_cdi_acum

        pfee_unit_acum_sem = max(0.0, excesso_cota) * taxa_pfee
        pfee_unit_dia = pfee_unit_acum_sem - pfee_unit_semestre_anterior
        pfee_unit_semestre_anterior = pfee_unit_acum_sem

        ret_cota_sem_pct = ((cota_atual / cota_base_sem) - 1.0) * 100.0 if cota_base_sem != 0 else 0.0
        ret_bench_sem_pct = ((cota_base_cdi_acum / cota_base_sem) - 1.0) * 100.0 if cota_base_sem != 0 else 0.0
        excesso_pct = ((cota_atual / cota_base_cdi_acum) - 1.0) * 100.0 if cota_base_cdi_acum != 0 else 0.0

        pfee_pct_cota = (pfee_unit_acum_sem / cota_atual) * 100.0 if cota_atual != 0 else 0.0
        pfee_rs_estimado = (pfee_pct_cota / 100.0) * pl_atual if pl_atual > 0 else 0.0

        linhas.append(
            {
                "DT_COMPTC": row["DT_COMPTC"],
                "Data_Fmt": pd.to_datetime(row["DT_COMPTC"]).strftime("%d/%m/%Y"),
                "Semestre": sem,
                "VL_PATRIM_LIQ": pl_atual,
                "Cota_Bruta": cota_atual,
                "Cota_Base_Sem": cota_base_sem,
                "Meta_CDI_Cota": cota_base_cdi_acum,
                "Benchmark_Negativo": "Sim" if benchmark_negativo else "Não",
                "Ret_Cota_Sem_Pct": ret_cota_sem_pct,
                "Ret_Bench_Sem_Pct": ret_bench_sem_pct,
                "Excesso_Sem_Pct": excesso_pct,
                "Pfee_Unit_Dia": pfee_unit_dia,
                "Pfee_Unit_Acum_Sem": pfee_unit_acum_sem,
                "Pfee_Pct_Cota": pfee_pct_cota,
                "Pfee_RS_Est": pfee_rs_estimado,
            }
        )

    return pd.DataFrame(linhas)


@st.cache_data(show_spinner=False)
def atualizar_dados_cvm(dt_ini: date, dt_fim: date) -> tuple[bool, str]:
    """
    Dispara a atualização incremental diária da CVM via API local (quando disponível)
    ou diretamente pelo módulo `coleta_cvm.py`, atualizando `dados_pl_cvm.csv` e limpando o cache.
    """
    payload_datas = {
        "data_inicio": dt_ini.strftime("%Y-%m-%d"),
        "data_fim": dt_fim.strftime("%Y-%m-%d"),
    }
    try:
        resp = requests.post(
            f"{API_BASE_URL}/fundos/sincronizar",
            json=payload_datas,
            timeout=120,
        )
        if resp.ok:
            st.cache_data.clear()
            return True, f"Dados CVM atualizados via API ({dt_ini.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')})."
    except Exception:
        pass

    try:
        df_atualizado = atualizar_base_diaria_cvm(
            data_inicio=dt_ini,
            data_fim=dt_fim,
            cnpj_alvo=CNPJS_SUPORTADOS,
            output_file=CSV_PATH,
        )
        st.cache_data.clear()
        if df_atualizado is not None and not df_atualizado.empty:
            return (
                True,
                f"Base local atualizada ({len(df_atualizado)} registros) para {dt_ini.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')}.",
            )
        return False, "Nenhum registro novo retornado pela CVM para o intervalo selecionado."
    except Exception as exc:
        st.cache_data.clear()
        return False, f"Falha ao atualizar dados da CVM: {exc}"


def carregar_base_local(csv_path: str, mtime: float) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"CNPJ_LIMPO": str}, low_memory=False)
    if "CNPJ_LIMPO" in df.columns:
        df["CNPJ_LIMPO"] = df["CNPJ_LIMPO"].apply(normalizar_cnpj)
    for col in ["VL_PATRIM_LIQ", "VL_QUOTA", "CAPTC_DIA", "RESG_DIA", "NR_COTST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["DT_COMPTC"] = pd.to_datetime(df["DT_COMPTC"], errors="coerce")
    return df.dropna(subset=["DT_COMPTC"]).sort_values(["CNPJ_LIMPO", "DT_COMPTC"]).reset_index(drop=True)


def obter_rotulo_fundo(cnpj_limpo: str, df_dados: pd.DataFrame) -> str:
    cfg = FUNDOS_CONFIG.get(cnpj_limpo, {})
    nome_cfg = str(cfg.get("nome") or "")
    if not df_dados.empty and "CNPJ_LIMPO" in df_dados.columns and "DENOM_SOCIAL" in df_dados.columns:
        sub_f = df_dados[df_dados["CNPJ_LIMPO"] == cnpj_limpo].dropna(subset=["DENOM_SOCIAL"])
        if not sub_f.empty:
            denom_csv = str(sub_f.iloc[-1]["DENOM_SOCIAL"]).strip()
            if denom_csv and not denom_csv.startswith("Fundo "):
                return f"{denom_csv} ({formatar_cnpj(cnpj_limpo)})"
    if nome_cfg:
        return f"{nome_cfg} ({formatar_cnpj(cnpj_limpo)})"
    return formatar_cnpj(cnpj_limpo)


@st.cache_data(ttl=3600, show_spinner=False)
def _buscar_serie_sgs_bcb(codigo_sgs: int, data_ini_str: str, data_fim_str: str) -> pd.DataFrame:
    try:
        resp = requests.get(
            BCB_SGS_URL.format(codigo=codigo_sgs),
            params={
                "formato": "json",
                "dataInicial": data_ini_str,
                "dataFinal": data_fim_str,
            },
            timeout=15,
        )
        if not resp.ok:
            return pd.DataFrame(columns=["DT_COMPTC", "VALOR"])
        dados = resp.json()
        if not dados:
            return pd.DataFrame(columns=["DT_COMPTC", "VALOR"])
        df_sgs = pd.DataFrame(dados)
        df_sgs["DT_COMPTC"] = pd.to_datetime(df_sgs["data"], format="%d/%m/%Y", errors="coerce")
        df_sgs["VALOR"] = pd.to_numeric(df_sgs["valor"], errors="coerce")
        return (
            df_sgs[["DT_COMPTC", "VALOR"]]
            .dropna()
            .sort_values("DT_COMPTC")
            .drop_duplicates(subset=["DT_COMPTC"], keep="last")
            .reset_index(drop=True)
        )
    except Exception:
        return pd.DataFrame(columns=["DT_COMPTC", "VALOR"])


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_cdi(dt_ini: date, dt_fim: date) -> pd.DataFrame:
    dt_ini_bcb = (dt_ini - timedelta(days=7)).strftime("%d/%m/%Y")
    dt_fim_bcb = dt_fim.strftime("%d/%m/%Y")
    return _buscar_serie_sgs_bcb(12, dt_ini_bcb, dt_fim_bcb)


@st.dialog("Aviso")
def mostrar_popup_cnpj_invalido(cnpj_informado: str, mensagem: str) -> None:
    st.markdown(
        f'<div style="color:#374151; font-size:0.95rem; line-height:1.45;">'
        f'{mensagem}<br><span class="cnpj-modal-code">{cnpj_informado}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# --- Carregamento da base ---
df_base = carregar_base_local(
    str(CSV_PATH),
    CSV_PATH.stat().st_mtime if CSV_PATH.exists() else 0.0,
)

# Estado inicial
_hoje_ini = datetime.now().date()
_sem_atual_padrao = f"{_hoje_ini.year}.{1 if _hoje_ini.month <= 6 else 2}"

if "filtro_sem_ini" not in st.session_state:
    st.session_state["filtro_sem_ini"] = _sem_atual_padrao
if "filtro_sem_fim" not in st.session_state:
    st.session_state["filtro_sem_fim"] = None
if "fundo_selecionado" not in st.session_state:
    st.session_state["fundo_selecionado"] = CNPJ_ALVO
if "cnpj_input_val" not in st.session_state:
    st.session_state["cnpj_input_val"] = formatar_cnpj(CNPJ_ALVO)
if "cnpj_popup_fechado_para" not in st.session_state:
    st.session_state["cnpj_popup_fechado_para"] = None
if "status_atualizacao_cvm" not in st.session_state:
    st.session_state["status_atualizacao_cvm"] = None


def _ao_selecionar_fundo() -> None:
    escolhido = normalizar_cnpj(st.session_state.get("sidebar_seletor_fundo", CNPJ_ALVO))
    if escolhido:
        st.session_state["fundo_selecionado"] = escolhido
        st.session_state["cnpj_input_val"] = formatar_cnpj(escolhido)
        st.session_state["cnpj_popup_fechado_para"] = None


def _ao_alterar_cnpj() -> None:
    digitado = normalizar_cnpj(st.session_state.get("cnpj_input_val", ""))
    if digitado in CNPJS_SUPORTADOS:
        st.session_state["fundo_selecionado"] = digitado
    st.session_state["cnpj_popup_fechado_para"] = None


# --- Sidebar: Seletor de Fundo, CNPJ e Filtros de Intervalo de Tempo ---
with st.sidebar:
    st.markdown("### CVM Funds Analytics")
    fundo_atual_sel = normalizar_cnpj(st.session_state.get("fundo_selecionado", CNPJ_ALVO))
    idx_seletor = CNPJS_SUPORTADOS.index(fundo_atual_sel) if fundo_atual_sel in CNPJS_SUPORTADOS else 0

    st.selectbox(
        "Selecionar Fundo",
        options=CNPJS_SUPORTADOS,
        index=idx_seletor,
        format_func=lambda c: obter_rotulo_fundo(c, df_base),
        key="sidebar_seletor_fundo",
        on_change=_ao_selecionar_fundo,
    )

    cnpj_input = st.text_input(
        "CNPJ do Fundo",
        placeholder=formatar_cnpj(CNPJ_ALVO),
        key="cnpj_input_val",
        on_change=_ao_alterar_cnpj,
    )

    st.markdown("---")
    st.markdown("### Intervalo de Tempo")
    opcoes_semestres = _gerar_opcoes_semestres(df_base, date(2018, 10, 1))
    sem_ini_atual = (
        st.session_state["filtro_sem_ini"]
        if st.session_state["filtro_sem_ini"] in opcoes_semestres
        else opcoes_semestres[0]
    )
    opcoes_sem_fim: list[str | None] = [None] + opcoes_semestres
    sem_fim_atual = (
        st.session_state["filtro_sem_fim"]
        if st.session_state["filtro_sem_fim"] in opcoes_semestres
        else None
    )

    sem_ini_sidebar = st.selectbox(
        "Semestre inicial",
        options=opcoes_semestres,
        index=opcoes_semestres.index(sem_ini_atual),
        key="sidebar_sem_ini",
    )
    sem_fim_sidebar = st.selectbox(
        "Semestre final",
        options=opcoes_sem_fim,
        index=opcoes_sem_fim.index(sem_fim_atual),
        format_func=lambda x: "Atual" if x is None else str(x),
        key="sidebar_sem_fim",
    )

    def _sem_tupla(s: str) -> tuple[int, int]:
        a, m = s.split(".")
        return (int(a), int(m))

    if st.session_state.get("status_atualizacao_cvm"):
        nivel_msg, texto_msg = st.session_state["status_atualizacao_cvm"]
        if nivel_msg == "success":
            st.success(texto_msg)
        else:
            st.warning(texto_msg)

    col_sb_limpar, col_sb_aplicar = st.columns(2)
    with col_sb_limpar:
        if st.button("Limpar", key="btn_limpar_data_sidebar", use_container_width=True):
            st.session_state["filtro_sem_ini"] = _sem_atual_padrao
            st.session_state["filtro_sem_fim"] = None
            st.rerun()
    with col_sb_aplicar:
        if st.button("Aplicar", key="btn_aplicar_data_sidebar", use_container_width=True):
            if sem_fim_sidebar is not None and _sem_tupla(sem_ini_sidebar) > _sem_tupla(sem_fim_sidebar):
                st.error("Semestre inicial maior que o final.")
            else:
                st.session_state["filtro_sem_ini"] = sem_ini_sidebar
                st.session_state["filtro_sem_fim"] = sem_fim_sidebar
                dt_ini_sync, _ = _limites_semestre(sem_ini_sidebar)
                dt_fim_sync = _limites_semestre(sem_fim_sidebar)[1] if sem_fim_sidebar else date.today()
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/fundos/sincronizar",
                        json={
                            "data_inicio": dt_ini_sync.strftime("%Y-%m-%d"),
                            "data_fim": dt_fim_sync.strftime("%Y-%m-%d"),
                        },
                        timeout=120,
                    )
                    if resp.ok:
                        st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()


# --- Validação do CNPJ e exibição do Pop-up de aviso ---
cnpj_bruto = (cnpj_input or "").strip()
cnpj_valido = False
mensagem_aviso_cnpj = ""

if cnpj_bruto:
    cnpj_valido, mensagem_aviso_cnpj = validar_cnpj(cnpj_bruto)
    if not cnpj_valido and st.session_state["cnpj_popup_fechado_para"] != cnpj_bruto:
        mostrar_popup_cnpj_invalido(cnpj_bruto, mensagem_aviso_cnpj)

cnpj_digitos = "".join(ch for ch in cnpj_bruto if ch.isdigit())
cnpj_limpo = cnpj_digitos.zfill(14) if cnpj_digitos else fundo_atual_sel

cfg_fundo = FUNDOS_CONFIG.get(cnpj_limpo, {})
denom_padrao_fundo = str(cfg_fundo.get("nome") or f"Fundo {formatar_cnpj(cnpj_limpo)}")
gestora_fundo = str(cfg_fundo.get("gestora") or GESTORA_PADRAO)
pfee_padrao_fundo = float(cfg_fundo.get("pfee_pct") or PFEE_PERCENTUAL_PADRAO)
cdi_padrao_fundo = float(cfg_fundo.get("cdi_pct") or PFEE_CDI_PCT_PADRAO)

sub = pd.DataFrame()
denom_atual = denom_padrao_fundo

if cnpj_valido and not df_base.empty:
    sub = df_base[df_base["CNPJ_LIMPO"] == cnpj_limpo].copy()
    if not sub.empty:
        sub = sub.sort_values("DT_COMPTC").reset_index(drop=True)
        denom_atual = str(sub.iloc[-1].get("DENOM_SOCIAL") or denom_padrao_fundo)

# --- Cabeçalho ---
st.markdown(f'<div class="hist-title">{denom_atual}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="hist-subtitle">CNPJ: {formatar_cnpj(cnpj_limpo)} • Gestora: {gestora_fundo} • Fonte: CVM / Regulamento</div>',
    unsafe_allow_html=True,
)


obs_textos_por_cnpj = {
    "29242441000181": (
        "Há incidência de taxa de performance mesmo quando o valor da cota do FUNDO "
        "for inferior ao seu valor por ocasião do último pagamento efetuado."
    ),
    "26179685000179": (
        "A taxa de performance somente será devida se o valor da cota do FUNDO ao final "
        "de cada período de cálculo for superior ao seu valor na data da última cobrança "
        "da taxa de performance ou no início do FUNDO, no caso da primeira cobrança."
    ),
}
obs_banner_html = ""
if cnpj_limpo in obs_textos_por_cnpj:
    obs_banner_html = f" • <b>Obs:</b> {obs_textos_por_cnpj[cnpj_limpo]}"

st.markdown(
    '<div class="rule-banner">'
    '<b>Art. 14 e Anexo:</b> 20,00% sobre a valorização da cota que, em cada semestre civil, '
    'exceder 100% do CDI acumulado'
    f'{obs_banner_html}'
    '</div>',
    unsafe_allow_html=True,
)

sem_ini_aplicado: str = st.session_state["filtro_sem_ini"]
sem_fim_aplicado: str | None = st.session_state["filtro_sem_fim"]
data_ini_aplicada, _ = _limites_semestre(sem_ini_aplicado)
data_fim_aplicada: date | None = _limites_semestre(sem_fim_aplicado)[1] if sem_fim_aplicado else None

sub_filtrado = sub.copy()
if not sub_filtrado.empty:
    sub_filtrado = sub_filtrado[sub_filtrado["DT_COMPTC"] >= pd.to_datetime(data_ini_aplicada)]
    if data_fim_aplicada is not None:
        sub_filtrado = sub_filtrado[sub_filtrado["DT_COMPTC"] <= pd.to_datetime(data_fim_aplicada)]

# --- Tela principal única: Taxa de Performance ---
col_titulo_pfee, col_btn_cvm = st.columns([3.2, 1.0], vertical_alignment="center")
with col_titulo_pfee:
    st.markdown("### Apuração da Taxa de Performance (*pfee*)")
with col_btn_cvm:
    if st.button("🔄 Atualizar dados CVM", key="btn_atualizar_cvm_topo", use_container_width=True, help="Atualiza os dados diários da CVM para o uso diário"):
        dt_ini_topo, _ = _limites_semestre(sem_ini_aplicado)
        dt_fim_topo = data_fim_aplicada if data_fim_aplicada is not None else date.today()
        with st.spinner("Coletando dados atualizados da CVM..."):
            ok_topo, msg_topo = atualizar_dados_cvm(dt_ini_topo, dt_fim_topo)
        st.session_state["status_atualizacao_cvm"] = ("success" if ok_topo else "warning", msg_topo)
        st.rerun()


if not sub_filtrado.empty:
    c_p1, c_p2, _ = st.columns([0.56, 0.56, 1.68], vertical_alignment="center")
    with c_p1:
        perc_pfee_input = st.number_input(
            "% Taxa de Performance",
            min_value=0.0,
            max_value=50.0,
            value=pfee_padrao_fundo,
            step=0.5,
            format="%.2f",
            key=f"perc_pfee_{cnpj_limpo}",
        )
    with c_p2:
        perc_cdi_input = st.number_input(
            "% do CDI (Benchmark)",
            min_value=0.0,
            max_value=200.0,
            value=cdi_padrao_fundo,
            step=1.0,
            format="%.1f",
            key=f"perc_cdi_{cnpj_limpo}",
        )

    dt_ini_pfee = sub_filtrado["DT_COMPTC"].min().date()
    dt_fim_pfee = sub_filtrado["DT_COMPTC"].max().date()
    df_cdi_pfee = carregar_cdi(dt_ini_pfee, dt_fim_pfee)

    df_pfee_calc = calcular_pfee_serie(
        sub_filtrado,
        df_cdi=df_cdi_pfee,
        perc_pfee=float(perc_pfee_input),
        perc_cdi=float(perc_cdi_input),
        respeitar_benchmark_negativo=True,
    )

    if not df_pfee_calc.empty:
        st.caption(
            f"Período recalculado: **{dt_ini_pfee.strftime('%d/%m/%Y')}** a **{dt_fim_pfee.strftime('%d/%m/%Y')}** "
            f"({len(df_pfee_calc)} pregões)"
        )
        ult_p = df_pfee_calc.iloc[-1]
        df_pfee_cron = df_pfee_calc.sort_values("DT_COMPTC", ascending=True)
        pfee_total_rs = float(df_pfee_cron.groupby("Semestre", sort=False)["Pfee_RS_Est"].last().sum())

        cards_pfee = [
            ("Cota Bruta (últ. dia)", formatar_cota(ult_p["Cota_Bruta"]), f"Data: {ult_p['Data_Fmt']}"),
            ("pfee a pagar ao fim (R$)", formatar_moeda(pfee_total_rs), "Fechamento de cada semestre"),
        ]
        itens_pfee = "".join(
            f'<div class="kpi-box">'
            f'<div class="kpi-title">{t}</div>'
            f'<div class="kpi-val">{v}</div>'
            f'<div class="kpi-sub">{s}</div>'
            f'</div>'
            for t, v, s in cards_pfee
        )
        st.markdown(f'<div class="kpi-row">{itens_pfee}</div>', unsafe_allow_html=True)

        df_pfee_plot = df_pfee_calc.copy()
        df_pfee_plot["Cota_Bruta_Fmt"] = df_pfee_plot["Cota_Bruta"].apply(formatar_cota)
        df_pfee_plot["CDI_Fmt"] = df_pfee_plot["Meta_CDI_Cota"].apply(formatar_cota)
        df_pfee_plot["Linha_Dagua_Fmt"] = df_pfee_plot["Cota_Base_Sem"].apply(formatar_cota)

        usar_linha_dagua = cnpj_limpo == "26179685000179"
        series_domain = ["Cota Bruta", "CDI"] + (["Linha d'água"] if usar_linha_dagua else [])
        series_range = ["#111827", "#6b7280"] + (["#d97706"] if usar_linha_dagua else [])
        series_dash = [[1, 0], [2, 2]] + ([[6, 3]] if usar_linha_dagua else [])

        linhas_frames = [
            pd.DataFrame(
                {
                    "DT_COMPTC": df_pfee_plot["DT_COMPTC"],
                    "Serie": "Cota Bruta",
                    "Valor_Cota": df_pfee_plot["Cota_Bruta"],
                }
            ),
            pd.DataFrame(
                {
                    "DT_COMPTC": df_pfee_plot["DT_COMPTC"],
                    "Serie": "CDI",
                    "Valor_Cota": df_pfee_plot["Meta_CDI_Cota"],
                }
            ),
        ]
        if usar_linha_dagua:
            linhas_frames.append(
                pd.DataFrame(
                    {
                        "DT_COMPTC": df_pfee_plot["DT_COMPTC"],
                        "Serie": "Linha d'água",
                        "Valor_Cota": df_pfee_plot["Cota_Base_Sem"],
                    }
                )
            )
        df_linhas_pfee = pd.concat(linhas_frames, ignore_index=True)

        hover_p = alt.selection_point(
            name="hover_pfee",
            fields=["DT_COMPTC"],
            nearest=True,
            on="pointerover",
            clear="pointerout",
            empty=False,
        )

        linhas_p = (
            alt.Chart(df_linhas_pfee)
            .mark_line(strokeWidth=2.4)
            .encode(
                x=alt.X("DT_COMPTC:T", title="Data", axis=alt.Axis(format="%d/%m/%Y")),
                y=alt.Y(
                    "Valor_Cota:Q",
                    title="Cota (R$)",
                    scale=alt.Scale(zero=False),
                ),
                color=alt.Color(
                    "Serie:N",
                    title="Legenda",
                    scale=alt.Scale(
                        domain=series_domain,
                        range=series_range,
                    ),
                    legend=alt.Legend(
                        orient="top",
                        direction="horizontal",
                        symbolType="stroke",
                        symbolStrokeWidth=3,
                        symbolSize=180,
                    ),
                ),
                strokeDash=alt.StrokeDash(
                    "Serie:N",
                    scale=alt.Scale(
                        domain=series_domain,
                        range=series_dash,
                    ),
                    legend=None,
                ),
            )
        )

        pontos_p = (
            alt.Chart(df_linhas_pfee)
            .mark_circle(size=70, stroke="#ffffff", strokeWidth=2)
            .encode(
                x="DT_COMPTC:T",
                y="Valor_Cota:Q",
                color=alt.Color(
                    "Serie:N",
                    scale=alt.Scale(
                        domain=series_domain,
                        range=series_range,
                    ),
                    legend=None,
                ),
                opacity=alt.condition(hover_p, alt.value(1), alt.value(0)),
            )
        )

        tooltip_campos = [
            alt.Tooltip("Data_Fmt:N", title="Data"),
            alt.Tooltip("Cota_Bruta_Fmt:N", title="Cota Bruta"),
            alt.Tooltip("CDI_Fmt:N", title="CDI"),
        ]
        if usar_linha_dagua:
            tooltip_campos.append(alt.Tooltip("Linha_Dagua_Fmt:N", title="Linha d'água"))

        regra_p = (
            alt.Chart(df_pfee_plot)
            .mark_rule(color="#9ca3af", strokeWidth=1.3, strokeDash=[4, 4])
            .encode(
                x="DT_COMPTC:T",
                opacity=alt.condition(hover_p, alt.value(1), alt.value(0)),
                tooltip=tooltip_campos,
            )
            .add_params(hover_p)
        )

        st.altair_chart(alt.layer(linhas_p, pontos_p, regra_p).properties(height=340), use_container_width=True)

        df_pfee_ord = df_pfee_calc.sort_values("DT_COMPTC", ascending=False).reset_index(drop=True)
        dt_unica = pd.to_datetime(df_pfee_ord["DT_COMPTC"]).dt.normalize()

        df_tab_pfee = pd.DataFrame(
            {
                "Data": dt_unica,
                "Semestre": df_pfee_ord["Semestre"],
                "PL": df_pfee_ord["VL_PATRIM_LIQ"].apply(formatar_moeda),
                "Cota Bruta": df_pfee_ord["Cota_Bruta"].apply(formatar_cota),
                "Cota Base": df_pfee_ord["Cota_Base_Sem"].apply(formatar_cota),
                "Cota CDI": df_pfee_ord["Meta_CDI_Cota"].apply(formatar_cota),
                "pfee % Cota": df_pfee_ord["Pfee_Pct_Cota"].apply(formatar_pct),
                "pfee Est. (R$)": df_pfee_ord["Pfee_RS_Est"].apply(formatar_moeda),
            }
        )

        st.dataframe(
            df_tab_pfee,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY"),
            },
        )
else:
    st.info("Nenhum dado histórico disponível para o fundo no período selecionado.")