from fastapi import FastAPI, HTTPException, Query
from motor_calculo import calcular_metricas_fundo, listar_datas_disponiveis, ranking_pl

app = FastAPI(
    title="API de Análise de PL - Fundos CVM",
    description="Motor de cálculo e consulta de Patrimônio Líquido, cota e cotistas de fundos.",
    version="1.0.0",
)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/datas")
def get_datas():
    return {"datas": listar_datas_disponiveis()}


@app.get("/fundos/ranking")
def get_ranking_pl(
    top_n: int = Query(10, ge=1, le=100),
    apenas_ativos: bool = Query(True),
    data_referencia: str | None = Query(None, description="Formato YYYY-MM-DD"),
):
    return {
        "top_n": top_n,
        "apenas_ativos": apenas_ativos,
        "data_referencia": data_referencia,
        "fundos": ranking_pl(
            top_n=top_n,
            apenas_ativos=apenas_ativos,
            data_referencia=data_referencia,
        ),
    }


@app.get("/fundos/{cnpj}/metricas")
def get_metricas_fundo(
    cnpj: str,
    data_inicio: str | None = Query(None, description="Formato YYYY-MM-DD"),
    data_fim: str | None = Query(None, description="Formato YYYY-MM-DD"),
):
    resultado = calcular_metricas_fundo(
        cnpj=cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Fundo ou período não encontrado na base.")
    return resultado