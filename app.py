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
    df = df.dropna(subset=["Órgão / Instituição"]).copy()
    for col in COLUNAS_OFICIAIS:
      if col not in df.columns:
        df[col] = ""
      df[col] = df[col].apply(limpar_valor)
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


def separar_local_e_orgao(
    texto_sem_contatos: str,
) -> tuple[str, str, str, str, str]:
  limpa = re.sub(
      r"\b(e-?mail|contato|telefone|tel|ramal\s*n[º°o.]*\s*\d*)\s*:?",
      "",
      texto_sem_contatos,
      flags=re.IGNORECASE,
  )
  limpa = limpa.replace("*", " ")

  observacoes = []
  for m_obs in re.finditer(r"\(([^)]+)\)", limpa):
    conteudo_par = m_obs.group(1).strip()
    if re.search(
        r"(enviar|ofício|oficio|agênc|agenc|nº|no\b|assunto|e-?mail|ramal|whatsapp|plantão|plantao)",
        conteudo_par,
        re.IGNORECASE,
    ):
      observacoes.append(conteudo_par)

  limpa = re.sub(r"\([^)]*\)", " ", limpa)
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
  obs_final = " | ".join(dict.fromkeys(observacoes))
  return orgao_base, cargo, autoridade, endereco_final, obs_final


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

    orgao, cargo, autoridade, endereco, obs = separar_local_e_orgao(sem_tel)

    if orgao or email_str or tel_str:
      novas_linhas.append([
          True,
          orgao,
          cargo,
          autoridade,
          tel_str,
          email_str,
          endereco,
          obs,
      ])

  return novas_linhas


def verificar_duplicados(
    linhas_df: pd.DataFrame, df_existente: pd.DataFrame
) -> list:
  if df_existente.empty or linhas_df.empty:
    return []
  duplicados = []
  for idx, r in linhas_df.iterrows():
    org_n = normalizar_busca(r.get("Órgão / Instituição", ""))
    mail_n = normalizar_busca(r.get("E-mail Institucional", ""))
    tel_n = re.sub(r"\D", "", str(r.get("Telefone / WhatsApp", "")))

    for _, ex in df_existente.iterrows():
      org_ex = normalizar_busca(ex.get("Órgão / Instituição", ""))
      mail_ex = normalizar_busca(ex.get("E-mail Institucional", ""))
      tel_ex = re.sub(r"\D", "", str(ex.get("Telefone / WhatsApp", "")))

      mesmo_org = bool(org_n and org_ex and org_n == org_ex)
      mesmo_mail = bool(mail_n and mail_ex and mail_n in mail_ex)
      mesmo_tel = bool(tel_n and tel_ex and len(tel_n) >= 8 and tel_n in tel_ex)

      if (mesmo_org and (mesmo_mail or mesmo_tel)) or (mesmo_mail and mesmo_tel):
        duplicados.append(
            f"Linha {idx + 1}: {r.get('Órgão / Instituição', '')}"
        )
        break
  return duplicados


def limpar_busca_callback():
  st.session_state["busca_termo"] = ""


df_base = carregar_dados()

aba_consulta, aba_alimentador, aba_editar = st.tabs([
    "🔍 Triagem e Consulta Rápida",
    "⚡ Téo — Alimentador de Endereços e Contatos",
    "✏️ Editar Registro",
])

with aba_consulta:
  if not df_base.empty:
    if "busca_termo" not in st.session_state:
      st.session_state["busca_termo"] = ""

    col_busca, col_limpar = st.columns([5, 1])
    with col_busca:
      termo = st.text_input(
          "🔍 Pesquisar Órgão, Autoridade, Cargo ou Local:",
          key="busca_termo",
          placeholder="Ex: forum, 3a vara, luziania, delegacia...",
      )
    with col_limpar:
      st.write("")
      st.write("")
      st.button("🧹 Limpar", on_click=limpar_busca_callback)

    if termo:
      mask = df_base.apply(lambda row: corresponde_busca(row, termo), axis=1)
      df_filtrado = df_base[mask]
    else:
      df_filtrado = df_base

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Registros encontrados", len(df_filtrado))
    m2.metric(
        "Com e-mail",
        int((df_filtrado["E-mail Institucional"] != "").sum()),
    )
    m3.metric(
        "Com telefone",
        int((df_filtrado["Telefone / WhatsApp"] != "").sum()),
    )
    m4.metric(
        "Com local/endereço",
        int((df_filtrado["Endereço / Local"] != "").sum()),
    )

    st.markdown("---")

    for pos, (_, row) in enumerate(df_filtrado.iterrows()):
      orgao = limpar_valor(row.get("Órgão / Instituição", ""))
      cargo = limpar_valor(row.get("Cargo / Função", ""))
      autoridade = limpar_valor(row.get("Nome da Autoridade", ""))
      telefone = limpar_valor(row.get("Telefone / WhatsApp", ""))
      email = limpar_valor(row.get("E-mail Institucional", ""))
      endereco = limpar_valor(row.get("Endereço / Local", ""))
      obs = limpar_valor(row.get("Observações", ""))
      wa_link = montar_link_whatsapp(telefone)

      st.markdown('<div class="contato-card">', unsafe_allow_html=True)
      st.subheader(f"🏢 {orgao}")

      if cargo and autoridade:
        st.write(f"**Cargo/Setor:** {cargo} — *{autoridade}*")
      elif autoridade:
        st.write(f"**Referência/Autoridade:** *{autoridade}*")
      elif cargo:
        st.write(f"**Cargo/Setor:** {cargo}")

      if endereco:
        st.write(f"📍 **Local:** {endereco}")

      col1, col2 = st.columns(2)
      with col1:
        if telefone:
          if wa_link:
            st.markdown(
                f"📞 **Telefone:** {telefone} • [💬 WhatsApp]({wa_link})"
            )
          else:
            st.write(f"📞 **Telefone:** {telefone}")
      with col2:
        if email:
          st.markdown(f"✉️ **E-mail:** [{email}](mailto:{email})")

      if obs:
        st.info(f"💡 **Observações:** {obs}")

      with st.expander(f"📋 Copiar contato rápido #{pos + 1}"):
        st.code(formatar_contato_copiar(row), language="text")

      st.markdown("</div>", unsafe_allow_html=True)

with aba_alimentador:
  st.subheader("⚡ Téo — Triar Lista, Conferir e Gravar na Planilha")
  st.markdown(
      "Cole a lista bruta abaixo. O **Téo** limpa asteriscos, junta e-mails"
      " soltos, separa órgão, cargo/autoridade, local e observações, e monta"
      " uma tabela editável antes de gravar."
  )

  texto_entrada = st.text_area("Cole sua lista aqui:", height=200)

  if st.button("🧪 Téo: Preparar e Conferir Lista", type="primary"):
    if texto_entrada.strip():
      linhas_preparadas = organizar_e_limpar_lista(texto_entrada)
      if linhas_preparadas:
        df_prev = pd.DataFrame(
            linhas_preparadas,
            columns=["Gravar?"] + COLUNAS_OFICIAIS,
        )
        st.session_state["teo_previa_df"] = df_prev
      else:
        st.warning("Não foi possível identificar registros válidos na lista.")
    else:
      st.warning("Cole uma lista antes de clicar no botão.")

  if "teo_previa_df" in st.session_state and not st.session_state[
      "teo_previa_df"
  ].empty:
    duplicados = verificar_duplicados(st.session_state["teo_previa_df"], df_base)
    if duplicados:
      st.warning(
          "⚠️ Possíveis registros já existentes na planilha: "
          + "; ".join(duplicados)
      )

    st.markdown(
        "**Pré-visualização editável** (você pode ajustar qualquer campo ou"
        " desmarcar `Gravar?` antes de salvar):"
    )
    df_editado = st.data_editor(
        st.session_state["teo_previa_df"],
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="editor_previa_teo",
    )

    if st.button("✅ Confirmar e Gravar Linhas Marcadas na Planilha"):
      with st.spinner("Gravando registros selecionados no Google Sheets..."):
        try:
          linhas_para_gravar = []
          for _, r in df_editado.iterrows():
            if bool(r.get("Gravar?", True)):
              linha_vals = [
                  limpar_valor(r.get(c, "")) for c in COLUNAS_OFICIAIS
              ]
              if any(linha_vals):
                linhas_para_gravar.append(linha_vals)

          if not linhas_para_gravar:
            st.warning("Nenhuma linha marcada para gravação.")
          else:
            aba_sheet = conectar_planilha()
            aba_sheet.append_rows(
                linhas_para_gravar, value_input_option="USER_ENTERED"
            )
            st.cache_data.clear()
            del st.session_state["teo_previa_df"]
            st.success(
                f"✅ Pronto! {len(linhas_para_gravar)} registro(s) gravado(s)"
                " diretamente na planilha!"
            )
            st.rerun()
        except Exception as e:
          st.error(f"Erro ao gravar na planilha: {type(e).__name__}: {e}")
          st.code(traceback.format_exc(), language="text")

with aba_editar:
  st.subheader("✏️ Editar Registro Existente na Planilha")
  if df_base.empty:
    st.info("Nenhum registro disponível para edição.")
  else:
    opcoes_reg = {
        f"Linha {int(r['_linha_sheet'])} — {r['Órgão / Instituição']}"
        + (f" ({r['E-mail Institucional']})" if r["E-mail Institucional"] else ""): int(
            r["_linha_sheet"]
        )
        for _, r in df_base.iterrows()
    }
    escolha_label = st.selectbox(
        "Selecione o registro para editar:", list(opcoes_reg.keys())
    )
    linha_alvo = opcoes_reg[escolha_label]
    registro_atual = df_base[df_base["_linha_sheet"] == linha_alvo].iloc[0]

    with st.form("form
