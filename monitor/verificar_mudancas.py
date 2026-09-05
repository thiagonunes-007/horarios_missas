#!/usr/bin/env python3
"""
Verifica as páginas "Horários de Missa" do site oficial da Arquidiocese de
Natal e envia um e-mail de alerta quando o conteúdo muda em relação à
última checagem.

Como funciona:
1. Baixa cada URL da lista PAGINAS.
2. Extrai só o miolo da página (ignora o menu/rodapé, que é igual em
   todo o site e não interessa).
3. Compara com o snapshot salvo em monitor/snapshots/<slug>.txt.
4. Se for diferente (ou se for a primeira vez), manda e-mail com o
   "antes/depois" e atualiza o snapshot.
5. Se não houver mudança em nenhuma página, não faz nada e não manda e-mail.
"""
import os
import re
import smtplib
import sys
import difflib
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PAGINAS = [
    ("urbano_1_e_2_pagina_a", "https://www.arquidiocesedenatal.org.br/cópia-horários-de-missa-2"),
    ("urbano_1_e_2_pagina_b", "https://www.arquidiocesedenatal.org.br/cópia-horários-de-missa"),
    ("norte_1_e_2",           "https://www.arquidiocesedenatal.org.br/horários-de-missa-2"),
    ("sul_1_2_e_3",           "https://www.arquidiocesedenatal.org.br/horários-de-missa-3"),
]

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

MARCA_INICIO = "Use tab to navigate through the menu items."
MARCA_FIM = "bottom of page"


def baixar_conteudo(url: str) -> str:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (monitor-horarios-missa)"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    texto = soup.get_text("\n")
    texto = re.sub(r"\n{2,}", "\n", texto).strip()

    ini = texto.find(MARCA_INICIO)
    fim = texto.find(MARCA_FIM)
    if ini != -1:
        texto = texto[ini + len(MARCA_INICIO):]
    if fim != -1:
        # recalcula fim já no texto cortado
        fim2 = texto.find(MARCA_FIM)
        if fim2 != -1:
            texto = texto[:fim2]
    return texto.strip()


def enviar_email(assunto: str, corpo: str):
    remetente = os.environ["SMTP_USER"]
    senha = os.environ["SMTP_PASS"]
    destinatario = os.environ["ALERT_EMAIL_TO"]

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(remetente, senha)
        servidor.sendmail(remetente, [destinatario], msg.as_string())


def main():
    houve_mudanca = False
    relatorios = []

    for slug, url in PAGINAS:
        snapshot_path = SNAPSHOTS_DIR / f"{slug}.txt"
        try:
            atual = baixar_conteudo(url)
        except Exception as e:
            relatorios.append(f"⚠️ Não consegui acessar {url}\nErro: {e}\n")
            continue

        if not snapshot_path.exists():
            snapshot_path.write_text(atual, encoding="utf-8")
            print(f"[{slug}] primeira checagem — snapshot salvo, sem alerta.")
            continue

        anterior = snapshot_path.read_text(encoding="utf-8")
        if anterior.strip() == atual.strip():
            print(f"[{slug}] sem mudanças.")
            continue

        houve_mudanca = True
        diff = "\n".join(difflib.unified_diff(
            anterior.splitlines(), atual.splitlines(),
            lineterm="", fromfile="antes", tofile="depois"
        ))
        relatorios.append(f"### Mudança detectada em: {url}\n\n{diff}\n")
        snapshot_path.write_text(atual, encoding="utf-8")

    if houve_mudanca:
        corpo = (
            "O site da Arquidiocese de Natal mudou uma ou mais páginas de "
            "Horários de Missa.\n\n" + "\n\n".join(relatorios) +
            "\n\nConfira o site oficial e, se necessário, atualize a "
            "planilha do app Horário de Missas."
        )
        enviar_email("⛪ Mudança nos horários de missa - Arquidiocese de Natal", corpo)
        print("E-mail de alerta enviado.")
    else:
        print("Nenhuma mudança encontrada. Nenhum e-mail enviado.")

    # sinaliza pro workflow se precisa commitar novos snapshots
    Path("monitor/.mudou").write_text("1" if houve_mudanca else "0")


if __name__ == "__main__":
    sys.exit(main())
