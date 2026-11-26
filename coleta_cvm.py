from __future__ import annotations

import io
import ssl
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
import urllib3
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_CADASTRO_FI = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
URL_REGISTRO_CLASSE = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
URL_INF_DIARIO_TEMPLATE = (
    "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
)
OUTPUT_FILE = Path("dados_pl_cvm.csv")

CNPJS_ALVO = [
    "29242441000181",
    "26179685000179",
]
CNPJ_ALVO = CNPJS_ALVO[0]
NOME_FUNDO_ALVO = "ABSOLUTE ICATU I PREV FIC DE FIF MULTIMERCADO"
DATA_INICIO_PADRAO = date(2021, 1, 1)


class CVMSSLAdapter(HTTPAdapter):
    """Adaptador SSL compatível com servidores da CVM."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        pool_kwargs["ssl_context"] = ctx
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def criar_sessao_cvm() -> requests.Session:
    session = requests.Session()
    session.verify = False
    session.mount("https://", CVMSSLAdapter())
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Connection": "close",
        }
    )
    return session


def baixar_com_retry(url: str, timeout: int = 180, tentativas: int = 3) -> bytes:
    """Baixa bytes da URL com nova conexão em caso de falha de rede ou SSL."""
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            sessao = criar_sessao_cvm()
            with sessao.get(url, timeout=timeout, stream=True) as resp:
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            ultimo_erro = exc
            print(f"[CVM] Tentativa {tentativa}/{tentativas} falhou ({exc}). Tentando novamente...")
            time.sleep(2 * tentativa)
    assert ultimo_erro is not None
    raise ultimo_erro


def normalizar_cnpj(cnpj: object) -> str:
    """Remove pontuação e garante 14 dígitos no CNPJ."""
    if pd.isna(cnpj):
        return ""
    digitos = "".join(ch for ch in str(cnpj) if ch.isdigit())
    return digitos.zfill(14) if digitos else ""


def normalizar_cnpjs_alvo(cnpjs_alvo: str | list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """Normaliza uma lista ou único CNPJ garantindo ordem sem duplicatas."""
    if isinstance(cnpjs_alvo, str):
        brutos = [cnpjs_alvo]
    else:
        brutos = list(cnpjs_alvo)

    normalizados: list[str] = []
    for item in brutos:
        c = normalizar_cnpj(item)
        if c and c not in normalizados:
            normalizados.append(c)
    return normalizados


def formatar_cnpj(cnpj: str) -> str:
    """Formata 14 dígitos no padrão XX.XXX.XXX/XXXX-XX."""
    c = normalizar_cnpj(cnpj)
    if len(c) != 14:
        return c
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def limpar_texto(serie: pd.Series) -> pd.Series:
    """Remove espaços extras e transforma string vazia em pd.NA."""
    s = serie.astype("string").str.strip()
    return s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})


def encontrar_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    """Busca coluna ignorando maiúsculas/minúsculas."""
    mapa = {c.lower(): c for c in df.columns}
    for cand in candidatos:
        if cand.lower() in mapa:
            return mapa[cand.lower()]
    return None


def gerar_competencias_yyyymm(dt_ini: date, dt_fim: date) -> list[tuple[int, int]]:
    """Gera pares (ano, mes) do intervalo [dt_ini, dt_fim]."""
    competencias: list[tuple[int, int]] = []
    ano, mes = dt_ini.year, dt_ini.month
    while (ano, mes) <= (dt_fim.year, dt_fim.month):
        competencias.append((ano, mes))
        if mes == 12:
            ano += 1
            mes = 1
        else:
            mes += 1
    return competencias


def baixar_cadastro_fundos(
    cnpjs_alvo: str | list[str] | tuple[str, ...] | set[str] = CNPJS_ALVO,
) -> pd.DataFrame:
    """Baixa e padroniza o cadastro geral de fundos (cad_fi.csv) filtrado aos CNPJs alvo."""
    alvos = set(normalizar_cnpjs_alvo(cnpjs_alvo))
    conteudo = baixar_com_retry(URL_CADASTRO_FI, timeout=120)
    df_cad = pd.read_csv(
        io.BytesIO(conteudo),
        sep=";",
        encoding="latin1",
        dtype=str,
        low_memory=False,
    )

    col_cnpj = encontrar_coluna(df_cad, ["CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO", "CNPJ"])
    col_nome = encontrar_coluna(df_cad, ["DENOM_SOCIAL", "DENOMINACAO_SOCIAL"])
    col_sit = encontrar_coluna(df_cad, ["SIT", "SITUACAO"])
    col_classe = encontrar_coluna(df_cad, ["CLASSE"])
    col_tp = encontrar_coluna(df_cad, ["TP_FUNDO", "TP_FUNDO_CLASSE"])

    if not col_cnpj:
        return pd.DataFrame(columns=["CNPJ_LIMPO"])

    out = pd.DataFrame({"CNPJ_LIMPO": df_cad[col_cnpj].apply(normalizar_cnpj)})
    if col_nome:
        out["DENOM_SOCIAL"] = limpar_texto(df_cad[col_nome])
    if col_sit:
        out["SIT"] = limpar_texto(df_cad[col_sit])
    if col_classe:
        out["CLASSE"] = limpar_texto(df_cad[col_classe])
    if col_tp:
        out["TP_FUNDO"] = limpar_texto(df_cad[col_tp])

    out = out[out["CNPJ_LIMPO"].isin(alvos)].copy()
    if "DENOM_SOCIAL" in out.columns:
        out = out.sort_values(
            by=["DENOM_SOCIAL"], na_position="last"
        ).drop_duplicates(subset=["CNPJ_LIMPO"], keep="first")
    else:
        out = out.drop_duplicates(subset=["CNPJ_LIMPO"])

    return out


def baixar_registro_classe(
    cnpjs_alvo: str | list[str] | tuple[str, ...] | set[str] = CNPJS_ALVO,
) -> pd.DataFrame:
    """Extrai dados de registro_fundo_classe.zip filtrados aos CNPJs alvo."""
    alvos = set(normalizar_cnpjs_alvo(cnpjs_alvo))
    conteudo = baixar_com_retry(URL_REGISTRO_CLASSE, timeout=180)
    registros: list[pd.DataFrame] = []

    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        for nome_arq in zf.namelist():
            if not nome_arq.endswith(".csv"):
                continue
            with zf.open(nome_arq) as csv_file:
                df_tmp = pd.read_csv(
                    csv_file,
                    sep=";",
                    encoding="latin1",
                    dtype=str,
                    low_memory=False,
                )

                col_nome = encontrar_coluna(
                    df_tmp,
                    ["DENOM_SOCIAL", "DENOMINACAO_SOCIAL", "NOME_FUNDO", "NOME_CLASSE"],
                )
                if not col_nome:
                    continue

                cols_cnpj = [c for c in df_tmp.columns if "cnpj" in c.lower()]
                for col_cnpj in cols_cnpj:
                    sub = pd.DataFrame(
                        {
                            "CNPJ_LIMPO": df_tmp[col_cnpj].apply(normalizar_cnpj),
                            "NOME_REG": limpar_texto(df_tmp[col_nome]),
                            "SIT_REG": limpar_texto(df_tmp[encontrar_coluna(df_tmp, ["SIT", "SITUACAO"])])
                            if encontrar_coluna(df_tmp, ["SIT", "SITUACAO"])
                            else pd.NA,
                        }
                    )
                    sub = sub[sub["CNPJ_LIMPO"].isin(alvos) & sub["NOME_REG"].notna()]
                    if not sub.empty:
                        registros.append(sub)

    if not registros:
        return pd.DataFrame(columns=["CNPJ_LIMPO", "NOME_REG", "SIT_REG"])

    df_reg = pd.concat(registros, ignore_index=True)
    return df_reg.drop_duplicates(subset=["CNPJ_LIMPO"], keep="first")


def baixar_informe_diario(
    ano: int,
    mes: int,
    cnpjs_alvo: str | list[str] | tuple[str, ...] | set[str] = CNPJS_ALVO,
) -> pd.DataFrame:
    """Baixa o Informe Diário da CVM e retorna apenas os registros dos CNPJs alvo."""
    alvos = set(normalizar_cnpjs_alvo(cnpjs_alvo))
    yyyymm = f"{ano}{mes:02d}"
    url = URL_INF_DIARIO_TEMPLATE.format(yyyymm=yyyymm)
    try:
        conteudo = baixar_com_retry(url, timeout=240)
    except Exception as exc:
        print(f"[CVM] Aviso: não foi possível baixar {yyyymm} ({exc}). Pulando competência.")
        return pd.DataFrame()

    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        csv_nomes = [nome for nome in zf.namelist() if nome.endswith(".csv")]
        if not csv_nomes:
            raise FileNotFoundError(f"Nenhum CSV encontrado dentro de {url}")
        with zf.open(csv_nomes[0]) as csv_file:
            df_inf = pd.read_csv(
                csv_file,
                sep=";",
                encoding="latin1",
                dtype=str,
                low_memory=False,
            )

    col_cnpj = encontrar_coluna(df_inf, ["CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO", "CNPJ"])
    if not col_cnpj:
        raise KeyError("Coluna de CNPJ não encontrada no Informe Diário.")

    df_inf["CNPJ_LIMPO"] = df_inf[col_cnpj].apply(normalizar_cnpj)
    return df_inf[df_inf["CNPJ_LIMPO"].isin(alvos)].copy()


def _competencias_existentes_por_cnpj(
    csv_path: Path,
    alvos_set: set[str],
) -> dict[str, set[tuple[int, int]]]:
    """
    Identifica quais competências (ano, mes) já possuem dados baixados para cada CNPJ
    no arquivo CSV local.
    """
    existentes: dict[str, set[tuple[int, int]]] = {c: set() for c in alvos_set}
    if not csv_path.exists():
        return existentes

    try:
        df_ex = pd.read_csv(csv_path, dtype={"CNPJ_LIMPO": str}, low_memory=False)
    except Exception:
        return existentes

    if df_ex.empty or "CNPJ_LIMPO" not in df_ex.columns or "DT_COMPTC" not in df_ex.columns:
        return existentes

    df_ex["CNPJ_LIMPO"] = df_ex["CNPJ_LIMPO"].apply(normalizar_cnpj)
    df_ex["DT_COMPTC"] = pd.to_datetime(df_ex["DT_COMPTC"], errors="coerce")
    df_ex = df_ex[df_ex["CNPJ_LIMPO"].isin(alvos_set)].dropna(subset=["DT_COMPTC"])

    for _, row in df_ex.iterrows():
        c = str(row["CNPJ_LIMPO"])
        dt_val = pd.Timestamp(row["DT_COMPTC"])
        existentes.setdefault(c, set()).add((int(dt_val.year), int(dt_val.month)))

    return existentes


def _salvar_csv_atomico(df_final: pd.DataFrame, destino: Path) -> None:
    """Grava o CSV de forma segura via arquivo temporário para evitar arquivo corrompido."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destino.with_suffix(f"{destino.suffix}.tmp")
    df_final.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(destino)


def coletar_pl_cvm(
    data_inicio: date = DATA_INICIO_PADRAO,
    data_fim: date | None = None,
    cnpj_alvo: str | list[str] | tuple[str, ...] | set[str] = CNPJS_ALVO,
    salvar_csv: bool = True,
    atualizacao_incremental: bool = True,
    rebaixar_mes_vigente: bool = True,
    output_file: Path | str = OUTPUT_FILE,
) -> pd.DataFrame:
    """
    Coleta e atualiza de forma incremental os dados de cota e patrimônio líquido da CVM
    no arquivo CSV local (`dados_pl_cvm.csv`).

    Na rotina diária (`atualizacao_incremental=True`):
    - Meses anteriores já presentes na base local para todos os CNPJs alvo são pulados.
    - O mês vigente (e meses ausentes) são baixados para capturar novos pregões diários.
    - Os registros são mesclados, ordenados e deduplicados por (CNPJ_LIMPO, DT_COMPTC).
    """
    destino = Path(output_file)
    alvos_lista = normalizar_cnpjs_alvo(cnpj_alvo)
    alvos_set = set(alvos_lista)
    dt_fim = data_fim or datetime.now().date()
    if data_inicio > dt_fim:
        raise ValueError("data_inicio não pode ser maior que data_fim.")

    hoje = datetime.now().date()
    mes_vigente = (hoje.year, hoje.month)

    competencias = gerar_competencias_yyyymm(data_inicio, dt_fim)
    existentes_por_cnpj = (
        _competencias_existentes_por_cnpj(destino, alvos_set)
        if atualizacao_incremental
        else {c: set() for c in alvos_set}
    )

    competencias_a_baixar: list[tuple[int, int, list[str]]] = []
    for ano, mes in competencias:
        comp = (ano, mes)
        if not atualizacao_incremental:
            cnpjs_faltantes = list(alvos_lista)
        elif rebaixar_mes_vigente and comp == mes_vigente:
            cnpjs_faltantes = list(alvos_lista)
        else:
            cnpjs_faltantes = [c for c in alvos_lista if comp not in existentes_por_cnpj.get(c, set())]

        if cnpjs_faltantes:
            competencias_a_baixar.append((ano, mes, cnpjs_faltantes))
        else:
            print(f"[CVM] Competência {mes:02d}/{ano} já atualizada na base local. Pulando.")

    partes_inf: list[pd.DataFrame] = []
    if competencias_a_baixar:
        cnpjs_fmt = ", ".join(formatar_cnpj(c) for c in alvos_lista)
        print(f"[CVM] Atualizando CNPJs {cnpjs_fmt} ({data_inicio} a {dt_fim})...")
        df_cad = baixar_cadastro_fundos(cnpjs_alvo=alvos_lista)
        df_reg = baixar_registro_classe(cnpjs_alvo=alvos_lista)

        for ano, mes, cnpjs_faltantes in competencias_a_baixar:
            print(
                f"[CVM] Baixando Informe Diário ({mes:02d}/{ano}) para "
                f"{', '.join(formatar_cnpj(c) for c in cnpjs_faltantes)}..."
            )
            df_mes = baixar_informe_diario(ano, mes, cnpjs_alvo=cnpjs_faltantes)
            if not df_mes.empty:
                partes_inf.append(df_mes)
    else:
        df_cad = pd.DataFrame(columns=["CNPJ_LIMPO"])
        df_reg = pd.DataFrame(columns=["CNPJ_LIMPO", "NOME_REG", "SIT_REG"])
        print("[CVM] Nenhuma competência nova para baixar. Base local já está em dia.")

    df_inf = pd.concat(partes_inf, ignore_index=True) if partes_inf else pd.DataFrame(columns=["CNPJ_LIMPO"])

    if not df_inf.empty:
        col_dt = encontrar_coluna(df_inf, ["DT_COMPTC"])
        if col_dt:
            df_inf["DT_COMPTC"] = pd.to_datetime(df_inf[col_dt], errors="coerce")
            df_inf = df_inf.dropna(subset=["DT_COMPTC"])
            df_inf = df_inf[
                (df_inf["DT_COMPTC"] >= pd.to_datetime(data_inicio))
                & (df_inf["DT_COMPTC"] <= pd.to_datetime(dt_fim))
            ]

    colunas_base = [
        c for c in ["CNPJ_LIMPO", "DT_COMPTC", "VL_PATRIM_LIQ", "VL_QUOTA", "NR_COTST"]
        if c in df_inf.columns
    ]
    df_novo = df_inf[colunas_base].merge(df_cad, on="CNPJ_LIMPO", how="left") if not df_inf.empty else pd.DataFrame()

    if not df_novo.empty:
        if "DENOM_SOCIAL" not in df_novo.columns:
            df_novo["DENOM_SOCIAL"] = pd.Series(pd.NA, dtype="string")
        else:
            df_novo["DENOM_SOCIAL"] = limpar_texto(df_novo["DENOM_SOCIAL"])

        if "SIT" not in df_novo.columns:
            df_novo["SIT"] = pd.Series(pd.NA, dtype="string")
        else:
            df_novo["SIT"] = limpar_texto(df_novo["SIT"])

        df_novo = df_novo.merge(df_reg, on="CNPJ_LIMPO", how="left")
        if "NOME_REG" in df_novo.columns:
            df_novo["DENOM_SOCIAL"] = df_novo["DENOM_SOCIAL"].fillna(df_novo["NOME_REG"])
        if "SIT_REG" in df_novo.columns:
            df_novo["SIT"] = df_novo["SIT"].fillna(df_novo["SIT_REG"])
        df_novo = df_novo.drop(columns=[c for c in ["NOME_REG", "SIT_REG"] if c in df_novo.columns])

        mapa_nomes_fallback = {
            CNPJ_ALVO: NOME_FUNDO_ALVO,
        }
        df_novo["DENOM_SOCIAL"] = df_novo["DENOM_SOCIAL"].fillna(
            df_novo["CNPJ_LIMPO"].map(mapa_nomes_fallback)
        )

    if destino.exists():
        df_existente = pd.read_csv(destino, dtype={"CNPJ_LIMPO": str}, low_memory=False)
        if "CNPJ_LIMPO" in df_existente.columns:
            df_existente["CNPJ_LIMPO"] = df_existente["CNPJ_LIMPO"].apply(normalizar_cnpj)
            df_existente = df_existente[df_existente["CNPJ_LIMPO"].isin(alvos_set)].copy()
        if "DT_COMPTC" in df_existente.columns:
            df_existente["DT_COMPTC"] = pd.to_datetime(df_existente["DT_COMPTC"], errors="coerce")
            df_existente = df_existente.dropna(subset=["DT_COMPTC"])
    else:
        df_existente = pd.DataFrame()

    df_final = pd.concat([df_existente, df_novo], ignore_index=True)
    if df_final.empty:
        return pd.DataFrame()

    for col in ["VL_PATRIM_LIQ", "VL_QUOTA", "NR_COTST"]:
        if col in df_final.columns:
            df_final[col] = pd.to_numeric(df_final[col], errors="coerce")

    df_final = (
        df_final.sort_values(["CNPJ_LIMPO", "DT_COMPTC"])
        .drop_duplicates(subset=["CNPJ_LIMPO", "DT_COMPTC"], keep="last")
        .reset_index(drop=True)
    )
    df_final["DT_COMPTC"] = df_final["DT_COMPTC"].dt.strftime("%Y-%m-%d")

    if salvar_csv:
        _salvar_csv_atomico(df_final, destino)
        print(f"[CVM] Arquivo salvo em '{destino.resolve()}' ({len(df_final)} registros).")

    return df_final


def atualizar_base_diaria_cvm(
    data_inicio: date = DATA_INICIO_PADRAO,
    data_fim: date | None = None,
    cnpj_alvo: str | list[str] | tuple[str, ...] | set[str] = CNPJS_ALVO,
    output_file: Path | str = OUTPUT_FILE,
) -> pd.DataFrame:
    """Atalho direto para atualização incremental diária da base local `dados_pl_cvm.csv`."""
    return coletar_pl_cvm(
        data_inicio=data_inicio,
        data_fim=data_fim or datetime.now().date(),
        cnpj_alvo=cnpj_alvo,
        salvar_csv=True,
        atualizacao_incremental=True,
        rebaixar_mes_vigente=True,
        output_file=output_file,
    )


if __name__ == "__main__":
    df_resultado = coletar_pl_cvm(
        data_inicio=date(2021, 1, 1),
        data_fim=datetime.now().date(),
        cnpj_alvo=CNPJS_ALVO,
        salvar_csv=True,
    )
    print(df_resultado.head(10))
