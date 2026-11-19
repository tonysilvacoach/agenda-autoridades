import difflib
import json
import re
import traceback
import unicodedata
import gspread
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Agenda de Autoridades - Fórum",
    page_icon="🏛️",
    layout="wide",
)
st.title("🏛️ Agenda de Autoridades e Órgãos")

SHEET_ID = "1PWxjWALBtB_SNNHIwPErRu5mVn5PEkZv3B8MEP79Hfg"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
)

COLUNAS_OFICIAIS = [
    "Órgão / Instituição",
    "Cargo / Função",
    "Nome da Autoridade",
    "Telefone / WhatsApp",
    "E-mail Institucional",
    "Endereço / Local",
    "Observações",
]


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
  # Tolerância a pequenas distorções/erros de digitação em palavras com 4+ letras
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
      str(v) for v in row_series.values if pd.notna(v) and str(v) != "nan"
  )
  alvo_norm = normalizar_busca(texto_linha)
  if termo_norm in alvo_norm:
    return True

  palavras_alvo = alvo_norm.split()
  termos_tokens = termo_norm.split()
  return all(
      token_parecido(tok, alvo_norm, palavras_alvo) for tok in termos_tokens
  )


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
    df = df.dropna(subset=["Órgão / Instituição"])
    return df
  except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    return pd.DataFrame()


def organizar_e_limpar_lista(texto_bruto: str) -> list:
  linhas_raw = [l.strip() for l in texto_bruto.splitlines() if l.strip()]
  linhas_unidas = []

  regex_email = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

  for linha in linhas_raw:
    if (
        linha.lower().startswith("destinatário:")
        or linha.lower().startswith("destinatario:")
        or linha == "*"
    ):
      continue
    so_email = regex_email.sub("", linha).replace("*", "").strip(" -:|")
    if linhas_unidas and not so_email and regex_email.search(linha):
      linhas_unidas[-1] += " " + linha
    else:
      linhas_unidas.append(linha)

  regex_telefone = re.compile(
      r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}-?\d{4}"
  )
  novas_linhas = []

  for linha in linhas_unidas:
    emails = regex_email.findall(linha)
    email_str = ", ".join(dict.fromkeys(emails))
    sem_email = regex_email.sub("", linha)

    telefones = regex_telefone.findall(sem_email)
    tel_str = " / ".join(dict.fromkeys([t.strip() for t in telefones]))
    sem_tel = regex_telefone.sub("", sem_email)

    limpa = re.sub(
        r"\b(e-?mail|contato|telefone|tel|ramal\s*n[º°o.]*\s*\d*)\s*:?",
        "",
        sem_tel,
        flags=re.IGNORECASE,
    )
    limpa = limpa.replace("*", " ").strip(" -–—|;,")
    limpa = re.sub(r"\s{2,}", " ", limpa)

    partes = [
        p.strip(" -–—|;,")
        for p in re.split(r"\s+[-–—|;]+\s+", limpa)
        if p.strip(" -–—|;,")
    ]
    orgao = partes[0] if len(partes) >= 1 else limpa
    autoridade = partes[1] if len(partes) >= 2 else ""
    endereco = " | ".join(partes[2:]) if len(partes) >= 3 else ""

    if orgao or email_str or tel_str:
      novas_linhas.append(
          [orgao, "", autoridade, tel_str, email_str, endereco, ""]
      )

  return novas_linhas


aba_consulta, aba_alimentador = st.tabs(
    ["🔍 Consulta Rápida", "⚡ Alimentador Automático (Grava Direto)"]
)

with aba_consulta:
  df = carregar_dados()
  if not df.empty:
    termo = st.text_input(
        "🔍 Pesquisar Órgão, Autoridade ou Cargo:",
        "",
        placeholder="Ex: forum, 3a vara, luziania, delegacia...",
    )
    if termo:
      mask = df.apply(lambda row: corresponde_busca(row, termo), axis=1)
      df_filtrado = df[mask]
    else:
      df_filtrado = df

    st.markdown(f"**Total de registros:** {len(df_filtrado)}")
    st.markdown("---")
    for _, row in df_filtrado.iterrows():
      orgao = str(row.get("Órgão / Instituição", ""))
      cargo = str(row.get("Cargo / Função", ""))
      autoridade = str(row.get("Nome da Autoridade", ""))
      telefone = str(row.get("Telefone / WhatsApp", ""))
      email = str(row.get("E-mail Institucional", ""))
      endereco = str(row.get("Endereço / Local", ""))
      obs = str(row.get("Observações", ""))

      with st.container():
        st.subheader(f"🏢 {orgao}")
        if cargo != "nan" and cargo:
          st.write(
              f"**Cargo/Setor:** {cargo}"
              + (
                  f" — *{autoridade}*"
                  if autoridade != "nan" and autoridade
                  else ""
              )
          )
        elif autoridade != "nan" and autoridade:
          st.write(f"**Referência/Autoridade:** *{autoridade}*")
        if endereco != "nan" and endereco:
          st.write(f"📍 **Local:** {endereco}")
        col1, col2 = st.columns(2)
        with col1:
          if telefone != "nan" and telefone:
            st.write(f"📞 **Telefone:** {telefone}")
        with col2:
          if email != "nan" and email:
            st.markdown(f"✉️ **E-mail:** [{email}](mailto:{email})")
        if obs != "nan" and obs:
          st.info(f"💡 **Observações:** {obs}")
        st.markdown("---")

with aba_alimentador:
  st.subheader("⚡ Colar Lista e Salvar Automaticamente na Planilha")
  st.markdown(
      "Cole a lista bruta abaixo. O sistema limpa asteriscos, junta e-mails"
      " soltos, organiza as colunas e adiciona direto no Google Sheets."
  )

  texto_entrada = st.text_area("Cole sua lista aqui:", height=220)

  if st.button("🚀 Organizar e Gravar Direto na Planilha", type="primary"):
    if texto_entrada.strip():
      with st.spinner("Organizando e salvando na planilha..."):
        try:
          linhas_prontas = organizar_e_limpar_lista(texto_entrada)
          aba_sheet = conectar_planilha()
          aba_sheet.append_rows(
              linhas_prontas, value_input_option="USER_ENTERED"
          )
          st.cache_data.clear()
          st.success(
              f"✅ Pronto! {len(linhas_prontas)} contatos foram organizados e"
              " gravados diretamente na planilha!"
          )
          st.dataframe(
              pd.DataFrame(linhas_prontas, columns=COLUNAS_OFICIAIS),
              use_container_width=True,
          )
        except Exception as e:
          st.error(f"Erro ao gravar na planilha: {type(e).__name__}: {e}")
          st.code(traceback.format_exc(), language="text")
    else:
      st.warning("Cole uma lista antes de clicar no botão.")
