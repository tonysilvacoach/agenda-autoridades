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
st.title("🤖 Téo — Triagem e Endereços Oficiais")
st.caption(
    "Agente de IA • Triagem e Endereços Oficiais (Órgãos, Autoridades e"
    " Contatos)"
)

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


def extrair_cargo_e_autoridade(trecho: str) -> tuple[str, str]:
  texto = trecho.strip(" -–—|;,")
  if not texto:
    return "", ""

  padrao_titulo_nome = re.compile(
      r"\b(Dr\.?|Dra\.?|Sgt\.?|Sargento|Ten\.?|Tenente|Cap\.?|Capitão|Capitao|Maj\.?|Major|Cel\.?|Coronel|Delegado\(a\)?|Delegado|Delegada|Promotor\(a\)?|Promotor|Promotora|Juiz\(a\)?|Juiz|Juíza|Diretor\(a\)?|Diretor|Diretora|Secretário\(a\)?|Secretario|Secretaria|Coordenador\(a\)?)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç]+){0,4})",
      re.IGNORECASE,
  )
  match = padrao_titulo_nome.search(texto)
  if match:
    cargo = match.group(1).strip()
    autoridade = match.group(2).strip()
    return cargo, autoridade

  if re.match(
      r"^(Diretor|Diretora|Delegado|Delegada|Promotor|Promotora|Juiz|Juíza|Coordenador|Secretário|Secretario)\b",
      texto,
      re.IGNORECASE,
  ):
    return texto, ""

  return "", texto


def separar_local_e_orgao(texto_sem_contatos: str) -> tuple[str, str, str, str]:
  limpa = re.sub(
      r"\b(e-?mail|contato|telefone|tel|ramal\s*n[º°o.]*\s*\d*)\s*:?",
      "",
      texto_sem_contatos,
      flags=re.IGNORECASE,
  )
  limpa = limpa.replace("*", " ")

  obs_parenteses = ""
  m_obs = re.search(
      r"\(([^)]*(?:enviar|ofício|oficio|agênc|agenc|nº|no)[^)]*)\)",
      limpa,
      re.IGNORECASE,
  )
  if m_obs:
    obs_parenteses = m_obs.group(1).strip()
    limpa = (limpa[: m_obs.start()] + " " + limpa[m_obs.end() :]).strip()

  limpa = re.sub(r"\s{2,}", " ", limpa).strip(" -–—|;,")

  partes = [
      p.strip(" -–—|;,")
      for p in re.split(r"\s+[-–—|;]+\s+", limpa)
      if p.strip(" -–—|;,")
  ]

  orgao_base = partes[0] if len(partes) >= 1 else limpa
  resto_partes = partes[1:] if len(partes) >= 2 else []

  locais = []
  outros = []

  padrao_endereco = re.compile(
      r"\b(Fórum\s+de\b|Forum\s+de\b|Rua\b|Av\.?|Avenida\b|Qd\.?|Quadra\b|Lt\.?|Lote\b|Setor\b|Centro\b|Parque\b|Rod\.?|Rodovia\b|BR-\d+|GO-\d+|MG-\d+|DF-\d+|BA-\d+)\b",
      re.IGNORECASE,
  )
  padrao_cidade_uf = re.compile(
      r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇa-zàéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇa-zàéíóúâêôãõç]+){0,3})\s*[/\-]\s*(GO|MG|DF|BA|TO|MT|MS|SP|RJ|RS|PR|SC)\b",
      re.IGNORECASE,
  )

  m_forum_colado = re.search(
      r"\s+(Fórum\s+de\s+[^\s]+(?:\s+[^\s]+){0,3})$",
      orgao_base,
      re.IGNORECASE,
  )
  if m_forum_colado:
    locais.append(m_forum_colado.group(1).strip())
    orgao_base = orgao_base[: m_forum_colado.start()].strip()

  m_uf_fim = re.search(
      r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇa-zàéíóúâêôãõç-]+)\s*[/\-]\s*(GO|MG|DF|BA|TO|MT|MS|SP|RJ|RS|PR|SC)\b$",
      orgao_base,
      re.IGNORECASE,
  )
  if m_uf_fim:
    locais.append(m_uf_fim.group(0).strip())

  for p in resto_partes:
    if padrao_endereco.search(p) or padrao_cidade_uf.search(p):
      locais.append(p)
    else:
      outros.append(p)

  cargo = ""
  autoridade = ""
  for item in outros:
    c, a = extrair_cargo_e_autoridade(item)
    if c and not cargo:
      cargo = c
    if a and not autoridade:
      autoridade = a
    elif not c and not a and not autoridade:
      autoridade = item

  if not autoridade and not cargo:
    c_base, a_base = extrair_cargo_e_autoridade(orgao_base)
    if c_base and a_base:
      cargo = c_base
      autoridade = a_base

  endereco_final = " | ".join(dict.fromkeys(locais))
  if obs_parenteses:
    endereco_final = (
        f"{endereco_final} ({obs_parenteses})".strip()
        if endereco_final
        else f"({obs_parenteses})"
    )

  return orgao_base, cargo, autoridade, endereco_final


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

    orgao, cargo, autoridade, endereco = separar_local_e_orgao(sem_tel)

    if orgao or email_str or tel_str:
      novas_linhas.append(
          [orgao, cargo, autoridade, tel_str, email_str, endereco, ""]
      )

  return novas_linhas


aba_consulta, aba_alimentador = st.tabs([
    "🔍 Triagem e Consulta Rápida",
    "⚡ Téo — Alimentador de Endereços e Contatos",
])

with aba_consulta:
  df = carregar_dados()
  if not df.empty:
    termo = st.text_input(
        "🔍 Pesquisar Órgão, Autoridade, Cargo ou Local:",
        "",
        placeholder="Ex: forum, 3a vara, formosa, luziania, delegacia...",
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
  st.subheader("⚡ Téo — Triar Lista e Gravar Direto na Planilha")
  st.markdown(
      "Cole a lista bruta abaixo. O **Téo** limpa asteriscos, junta e-mails"
      " soltos, separa órgão, cargo/autoridade e endereço oficial, e salva"
      " direto no Google Sheets."
  )

  texto_entrada = st.text_area("Cole sua lista aqui:", height=220)

  if st.button("🚀 Téo: Organizar e Gravar na Planilha", type="primary"):
    if texto_entrada.strip():
      with st.spinner("Téo organizando e salvando na planilha..."):
        try:
          linhas_prontas = organizar_e_limpar_lista(texto_entrada)
          aba_sheet = conectar_planilha()
          aba_sheet.append_rows(
              linhas_prontas, value_input_option="USER_ENTERED"
          )
          st.cache_data.clear()
          st.success(
              f"✅ Pronto! O Téo organizou e gravou {len(linhas_prontas)}"
              " contato(s) diretamente na planilha!"
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
