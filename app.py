import difflib
import json
import re
import traceback
import unicodedata
import gspread
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Téo • Triagem e Endereços Oficiais — Fórum de Formosa",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .teo-banner {
        background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
        color: #f8fafc;
        padding: 18px 22px;
        border-radius: 12px;
        border-left: 6px solid #38bdf8;
        margin-bottom: 14px;
    }
    .teo-banner h2 {
        margin: 0 0 4px 0;
        color: #ffffff;
        font-size: 1.55rem;
    }
    .teo-banner p {
        margin: 0;
        color: #cbd5e1;
        font-size: 0.95rem;
    }
    .contato-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .teo-footer {
        margin-top: 28px;
        padding-top: 14px;
        border-top: 1px solid #334155;
        text-align: center;
        color: #94a3b8;
        font-size: 0.88rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="teo-banner">
        <h2>🤖 Téo — Triagem e Endereços Oficiais</h2>
        <p>Agente de IA do departamento de contatos, órgãos, autoridades e endereços • Consulta rápida, triagem inteligente e edição direta</p>
    </div>
    """,
    unsafe_allow_html=True,
)

SHEET_ID = "1PWxjWALBtB_SNNHIwPErRu5mVn5PEkZv3B8MEP79Hfg"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
)
HEADER_ROW_INDEX = 5

COLUNAS_OFICIAIS = [
    "Órgão / Instituição",
    "Cargo / Função",
    "Nome da Autoridade",
    "Telefone / WhatsApp",
    "E-mail Institucional",
    "Endereço / Local",
    "Observações",
]


def limpar_valor(val) -> str:
  if val is None or pd.isna(val):
    return ""
  s = str(val).strip()
  return "" if s.lower() == "nan" else s


def normalizar_busca(texto: str) -> str:
  if not texto:
    return ""
  texto = str(texto).lower()
  texto = texto.replace("ª", "a").replace("º", "o").replace("°", "o")
  texto = unicodedata.normalize("NFKD", texto)
  texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
  texto = re.sub(r"[^a-z0-9@.\s]", " ", texto)
  texto = re.sub(r"\s+", " ", texto).strip()
  return texto


def token_parecido(termo_tok: str, alvo_norm: str, palavras_alvo: list) -> bool:
  if termo_tok in alvo_norm:
    return True
  if len(termo_tok) >= 4:
    for pal in palavras_alvo:
      if abs(len(pal) - len(termo_tok)) <= 2:
        ratio = difflib.SequenceMatcher(None, termo_tok, pal).ratio()
        if ratio >= 0.78:
          return True
  return False


def corresponde_busca(row_series: pd.Series, termo: str) -> bool:
  termo_norm = normalizar_busca(termo)
  if not termo_norm:
    return True

  texto_linha = " ".join(
      limpar_valor(v) for v in row_series.values if limpar_valor(v)
  )
  alvo_norm = normalizar_busca(texto_linha)
  if termo_norm in alvo_norm:
    return True

  palavras_alvo = alvo_norm.split()
  termos_tokens = termo_norm.split()
  return all(
      token_parecido(tok, alvo_norm, palavras_alvo) for tok in termos_tokens
  )


def montar_link_whatsapp(telefone_texto: str) -> str:
  if not telefone_texto:
    return ""
  digitos = re.sub(r"\D", "", telefone_texto.split("/")[0])
  if len(digitos) in (10, 11):
    return f"https://wa.me/55{digitos}"
  if len(digitos) in (12, 13) and digitos.startswith("55"):
    return f"https://wa.me/{digitos}"
  return ""


def formatar_contato_copiar(row: pd.Series) -> str:
  orgao = limpar_valor(row.get("Órgão / Instituição", ""))
  cargo = limpar_valor(row.get("Cargo / Função", ""))
  autoridade = limpar_valor(row.get("Nome da Autoridade", ""))
  telefone = limpar_valor(row.get("Telefone / WhatsApp", ""))
  email = limpar_valor(row.get("E-mail Institucional", ""))
  endereco = limpar_valor(row.get("Endereço / Local", ""))
  obs = limpar_valor(row.get("Observações", ""))

  partes = []
  if orgao:
    partes.append(orgao)
  if cargo and autoridade:
    partes.append(f"{cargo}: {autoridade}")
  elif autoridade:
    partes.append(autoridade)
  elif cargo:
    partes.append(cargo)
  if telefone:
    partes.append(f"Tel: {telefone}")
  if email:
    partes.append(f"E-mail: {email}")
  if endereco:
    partes.append(f"Local: {endereco}")
  if obs:
    partes.append(f"Obs: {obs}")
  return " | ".join(partes)


def conectar_planilha():
  raw_secret = st.secrets["gcp_json"]
  if isinstance(raw_secret, str):
    credenciais_dict = json.loads(raw_secret)
  else:
    credenciais_dict = dict(raw_secret)

  if "private_key" in credenciais_dict and isinstance(
      credenciais_dict["private_key"], str
  ):
    credenciais_dict["private_key"] = credenciais_dict["private_key"].replace(
        "\\n", "\n"
    )

  gc = gspread.service_account_from_dict(credenciais_dict)
  planilha = gc.open_by_key(SHEET_ID)
  return planilha.sheet1


@st.cache_data(ttl=10)
def carregar_dados():
  try:
    df = pd.read_csv(SHEET_URL, skiprows=4)
    df["_linha_sheet"] = df.index + HEADER_ROW_INDEX + 1
