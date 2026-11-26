from __future__ import annotations

from pathlib import Path
import pandas as pd

CSV_PATH = Path("dados_pl_cvm.csv")


def normalizar_cnpj(cnpj: str) -> str:
    digitos = "".join(ch for ch in str(cnpj) if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def carregar_base(csv_path: Path = CSV_PATH) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Arquivo '{csv_path}' não encontrado. Rode o coleta_cvm.py primeiro."
        )

    df = pd.read_csv(csv_path, dtype={"CNPJ_LIMPO": str}, low_memory=False)
    for col in ["VL_PATRIM_LIQ", "VL_QUOTA", "NR_COTST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["DT_COMPTC"] = pd.to_datetime(df["DT_COMPTC"], errors="coerce")
    df = df.dropna(subset=["DT_COMPTC"]).sort_values(["CNPJ_LIMPO", "DT_COMPTC"]).reset_index(drop=True)
    return df


def listar_datas_disponiveis(csv_path: Path = CSV_PATH) -> list[str]:
    """Retorna todas as datas de competência disponíveis na base (YYYY-MM-DD)."""
    df = carregar_base(csv_path)
    datas = sorted(df["DT_COMPTC"].dt.strftime("%Y-%m-%d").unique().tolist())
    return datas


def calcular_metricas_fundo(
    cnpj: str,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    csv_path: Path = CSV_PATH,
) -> dict:
    """Calcula métricas de PL, cota e base de cotistas para um fundo em um intervalo de datas."""
    df = carregar_base(csv_path)
    cnpj_limpo = normalizar_cnpj(cnpj)

    sub = df[df["CNPJ_LIMPO"] == cnpj_limpo].copy()
    if sub.empty:
        return {}

    if data_inicio:
        sub = sub[sub["DT_COMPTC"] >= pd.to_datetime(data_inicio)]
    if data_fim:
        sub = sub[sub["DT_COMPTC"] <= pd.to_datetime(data_fim)]

    if sub.empty:
        return {}

    primeiro = sub.iloc[0]
    ultimo = sub.iloc[-1]

    pl_inicial = float(primeiro["VL_PATRIM_LIQ"]) if pd.notna(primeiro["VL_PATRIM_LIQ"]) else None
    pl_atual = float(ultimo["VL_PATRIM_LIQ"]) if pd.notna(ultimo["VL_PATRIM_LIQ"]) else None
    pl_medio = float(sub["VL_PATRIM_LIQ"].mean()) if sub["VL_PATRIM_LIQ"].notna().any() else None

    variacao_pl_abs = (
        round(pl_atual - pl_inicial, 2)
        if pl_inicial is not None and pl_atual is not None
        else None
    )
    variacao_pl_pct = (
        round(((pl_atual / pl_inicial) - 1) * 100, 4)
        if pl_inicial not in (None, 0) and pl_atual is not None
        else None
    )

    cota_inicial = float(primeiro["VL_QUOTA"]) if pd.notna(primeiro.get("VL_QUOTA")) else None
    cota_atual = float(ultimo["VL_QUOTA"]) if pd.notna(ultimo.get("VL_QUOTA")) else None
    retorno_cota_pct = (
        round(((cota_atual / cota_inicial) - 1) * 100, 4)
        if cota_inicial not in (None, 0) and cota_atual is not None
        else None
    )

    cotistas_atual = int(ultimo["NR_COTST"]) if pd.notna(ultimo.get("NR_COTST")) else None
    pl_por_cotista = (
        round(pl_atual / cotistas_atual, 2)
        if pl_atual is not None and cotistas_atual not in (None, 0)
        else None
    )

    return {
        "cnpj": cnpj_limpo,
        "denominacao_social": str(ultimo.get("DENOM_SOCIAL") or ""),
        "situacao": str(ultimo.get("SIT") or ""),
        "classe": str(ultimo.get("CLASSE") or ""),
        "data_inicio": str(primeiro["DT_COMPTC"].date()),
        "data_fim": str(ultimo["DT_COMPTC"].date()),
        "pl_inicial": pl_inicial,
        "pl_atual": pl_atual,
        "pl_medio": round(pl_medio, 2) if pl_medio is not None else None,
        "variacao_pl_abs": variacao_pl_abs,
        "variacao_pl_pct": variacao_pl_pct,
        "retorno_cota_pct": retorno_cota_pct,
        "nr_cotistas_atual": cotistas_atual,
        "pl_medio_por_cotista": pl_por_cotista,
        "serie_historica": [
            {
                "data": str(row["DT_COMPTC"].date()),
                "pl": float(row["VL_PATRIM_LIQ"]) if pd.notna(row["VL_PATRIM_LIQ"]) else None,
                "cota": float(row["VL_QUOTA"]) if pd.notna(row.get("VL_QUOTA")) else None,
                "cotistas": int(row["NR_COTST"]) if pd.notna(row.get("NR_COTST")) else None,
            }
            for _, row in sub.iterrows()
        ],
    }


def ranking_pl(
    top_n: int = 10,
    apenas_ativos: bool = True,
    data_referencia: str | None = None,
    csv_path: Path = CSV_PATH,
) -> list[dict]:
    """Retorna os fundos com maior PL na data informada (ou na última data disponível)."""
    df = carregar_base(csv_path)
    if apenas_ativos and "SIT" in df.columns:
        df = df[df["SIT"].astype(str).str.upper() == "EM FUNCIONAMENTO NORMAL"]

    if data_referencia:
        dt_alvo = pd.to_datetime(data_referencia)
        base_atual = df[df["DT_COMPTC"] == dt_alvo].copy()
    else:
        ultimas_datas = df.groupby("CNPJ_LIMPO", as_index=False)["DT_COMPTC"].max()
        base_atual = df.merge(ultimas_datas, on=["CNPJ_LIMPO", "DT_COMPTC"], how="inner")

    base_atual = base_atual.dropna(subset=["VL_PATRIM_LIQ"]).sort_values(
        "VL_PATRIM_LIQ", ascending=False
    )

    return [
        {
            "cnpj": row["CNPJ_LIMPO"],
            "denominacao_social": str(row.get("DENOM_SOCIAL") or ""),
            "situacao": str(row.get("SIT") or ""),
            "data_referencia": str(row["DT_COMPTC"].date()),
            "vl_quota": float(row["VL_QUOTA"]) if pd.notna(row.get("VL_QUOTA")) else None,
            "pl_atual": float(row["VL_PATRIM_LIQ"]),
            "nr_cotistas": int(row["NR_COTST"]) if pd.notna(row.get("NR_COTST")) else None,
        }
        for _, row in base_atual.head(top_n).iterrows()
    ]