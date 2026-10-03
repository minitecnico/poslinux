#!/usr/bin/env python3
"""
Pós-install Linux - servidor local

Abre uma página no navegador onde você escolhe os programas e clica em
"Instalar". O servidor roda os comandos no seu computador e mostra o
progresso ao vivo.

Uso (um comando só, como usuário normal, SEM sudo):
   curl -fsSL URL_DO_ARQUIVO | python3 -
   ou, com o arquivo baixado:  python3 pos-install.py

Só usa a biblioteca padrão do Python, então não precisa instalar nada.

SEGURANÇA
- Escuta apenas em 127.0.0.1 (ninguém na rede acessa).
- Exige um token aleatório (vai na URL aberta pelo servidor).
- A página nunca envia comandos: só IDs do catálogo ou nomes de pacote,
  que são validados com regras estritas e escapados antes de virar comando.
"""

import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORTA_INICIAL = 8765
TOKEN = secrets.token_urlsafe(16)

# ======================================================================
#  DADOS - edite aqui para adicionar distros ou programas
#  (os comandos rodam como root, por isso não levam "sudo")
# ======================================================================

DISTROS = {
    "apt": {
        "nome": "Ubuntu / Debian", "sub": "apt (Mint, Pop!_OS)",
        "update": "apt-get update && apt-get upgrade -y",
        "install": "apt-get install -y",
    },
    "dnf": {
        "nome": "Fedora", "sub": "dnf",
        "update": "dnf upgrade -y",
        "install": "dnf install -y",
    },
    "pacman": {
        "nome": "Arch", "sub": "pacman (Manjaro, EndeavourOS)",
        "update": "pacman -Syu --noconfirm",
        "install": "pacman -S --noconfirm --needed",
    },
    "zypper": {
        "nome": "openSUSE", "sub": "zypper",
        "update": "zypper -n refresh && zypper -n update",
        "install": "zypper -n install",
    },
}

# Em cada programa, "pkg" tem uma entrada por distro:
#   "nome-do-pacote"  -> instalado pelo gerenciador da distro
#   "flatpak:ID"      -> instalado via Flatpak (IDs em flathub.org)
#   "cmd:comando"     -> comando próprio
def igual(n):
    return {d: n for d in DISTROS}


def flatpak(app_id):
    return igual("flatpak:" + app_id)


DOCKER_POS = "systemctl enable --now docker && usermod -aG docker \"${SUDO_USER:-$USER}\""


def docker(instalar):
    return "cmd:" + instalar + " && " + DOCKER_POS


CATALOGO = [
    # Navegadores
    {"id": "chrome", "cat": "Navegadores", "icone": "🌐", "nome": "Google Chrome", "pkg": flatpak("com.google.Chrome")},
    {"id": "brave", "cat": "Navegadores", "icone": "🦁", "nome": "Brave", "pkg": flatpak("com.brave.Browser")},
    {"id": "firefox", "cat": "Navegadores", "icone": "🦊", "nome": "Firefox",
     "pkg": {"apt": "firefox", "dnf": "firefox", "pacman": "firefox", "zypper": "MozillaFirefox"}},

    # Escritório e mídia
    {"id": "libreoffice", "cat": "Escritório e mídia", "icone": "📄", "nome": "LibreOffice",
     "pkg": {"apt": "libreoffice", "dnf": "libreoffice", "pacman": "libreoffice-fresh", "zypper": "libreoffice"}},
    {"id": "vlc", "cat": "Escritório e mídia", "icone": "🎬", "nome": "VLC", "pkg": igual("vlc")},
    {"id": "gimp", "cat": "Escritório e mídia", "icone": "🎨", "nome": "GIMP", "pkg": igual("gimp")},
    {"id": "obs", "cat": "Escritório e mídia", "icone": "🎥", "nome": "OBS Studio", "pkg": flatpak("com.obsproject.Studio")},
    {"id": "spotify", "cat": "Escritório e mídia", "icone": "🎧", "nome": "Spotify", "pkg": flatpak("com.spotify.Client")},
    {"id": "qbittorrent", "cat": "Escritório e mídia", "icone": "⬇️", "nome": "qBittorrent", "pkg": igual("qbittorrent")},

    # Comunicação e jogos
    {"id": "telegram", "cat": "Comunicação e jogos", "icone": "✈️", "nome": "Telegram", "pkg": flatpak("org.telegram.desktop")},
    {"id": "discord", "cat": "Comunicação e jogos", "icone": "💬", "nome": "Discord", "pkg": flatpak("com.discordapp.Discord")},
    {"id": "steam", "cat": "Comunicação e jogos", "icone": "🎮", "nome": "Steam", "pkg": flatpak("com.valvesoftware.Steam")},

    # Desenvolvimento
    {"id": "vscode", "cat": "Desenvolvimento", "icone": "🧑‍💻", "nome": "VS Code", "pkg": flatpak("com.visualstudio.code")},
    {"id": "git", "cat": "Desenvolvimento", "icone": "🔀", "nome": "Git", "pkg": igual("git")},
    {"id": "build", "cat": "Desenvolvimento", "icone": "🔧", "nome": "Ferramentas de compilação",
     "pkg": {"apt": "build-essential", "dnf": "cmd:dnf install -y @development-tools",
             "pacman": "base-devel", "zypper": "cmd:zypper -n install -t pattern devel_basis"}},
    {"id": "python", "cat": "Desenvolvimento", "icone": "🐍", "nome": "Python + pip",
     "pkg": {"apt": "python3 python3-pip", "dnf": "python3 python3-pip",
             "pacman": "python python-pip", "zypper": "python3 python3-pip"}},
    {"id": "node", "cat": "Desenvolvimento", "icone": "🟢", "nome": "Node.js + npm", "pkg": igual("nodejs npm")},
    {"id": "docker", "cat": "Desenvolvimento", "icone": "🐳", "nome": "Docker",
     "pkg": {"apt": docker("apt-get install -y docker.io"),
             "dnf": docker("dnf install -y moby-engine"),
             "pacman": docker("pacman -S --noconfirm --needed docker"),
             "zypper": docker("zypper -n install docker")}},

    # Terminal
    {"id": "curl", "cat": "Terminal", "icone": "📡", "nome": "curl", "pkg": igual("curl")},
    {"id": "wget", "cat": "Terminal", "icone": "📥", "nome": "wget", "pkg": igual("wget")},
    {"id": "vim", "cat": "Terminal", "icone": "📝", "nome": "Vim", "pkg": igual("vim")},
    {"id": "htop", "cat": "Terminal", "icone": "📊", "nome": "htop", "pkg": igual("htop")},
    {"id": "tmux", "cat": "Terminal", "icone": "🪟", "nome": "tmux", "pkg": igual("tmux")},
    {"id": "tree", "cat": "Terminal", "icone": "🌳", "nome": "tree", "pkg": igual("tree")},
    {"id": "unzip", "cat": "Terminal", "icone": "🗜️", "nome": "unzip", "pkg": igual("unzip")},
    {"id": "fastfetch", "cat": "Terminal", "icone": "💻", "nome": "fastfetch", "pkg": igual("fastfetch")},
]

POR_ID = {p["id"]: p for p in CATALOGO}

# ======================================================================
#  Página (interface Vue) embutida: assim o programa é UM arquivo só
# ======================================================================

HTML = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pós-install Linux</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;500;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #eef1f6;
    --surface: #ffffff;
    --ink: #14213d;
    --muted: #5b667f;
    --line: #d5dbe8;
    --accent: #2f5bff;
    --accent-ink: #ffffff;
    --sel: #fff3c4;
    --sel-line: #d99a00;
    --ok: #178a52;
    --bad: #c62f3a;
    --term: #0e1630;
    --term-ink: #dfe6ff;
    --term-dim: #8e9ac4;
    --font: "Bricolage Grotesque", system-ui, -apple-system, "Segoe UI", sans-serif;
    --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0b1020;
      --surface: #141b33;
      --ink: #e8ecfa;
      --muted: #9aa5c6;
      --line: #27304f;
      --accent: #7b9bff;
      --accent-ink: #0b1020;
      --sel: #3a3112;
      --sel-line: #e0a800;
      --ok: #55d68f;
      --bad: #ff7a85;
      --term: #060a17;
    }
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: var(--font); font-size: 16px; line-height: 1.5;
  }
  [v-cloak] { display: none; }
  button { font: inherit; color: inherit; cursor: pointer; }
  :focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }

  .page { max-width: 1240px; margin: 0 auto; padding: 40px 24px 64px; }

  header.top { margin-bottom: 36px; max-width: 680px; }
  header.top h1 {
    margin: 0 0 8px; font-size: clamp(2.2rem, 5vw, 3.4rem);
    line-height: 1.02; font-weight: 800; letter-spacing: -0.03em;
  }
  header.top p { margin: 0; color: var(--muted); font-size: 1.1rem; }

  .layout { display: grid; gap: 32px; grid-template-columns: minmax(0, 1fr); align-items: start; }
  @media (min-width: 1000px) { .layout { grid-template-columns: minmax(0, 1fr) 420px; } }

  section + section { margin-top: 36px; }
  h2 {
    display: flex; align-items: center; gap: 12px;
    margin: 0 0 16px; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em;
  }
  .n {
    display: inline-grid; place-items: center; width: 30px; height: 30px;
    border-radius: 50%; background: var(--ink); color: var(--bg);
    font-size: 0.95rem; font-weight: 700;
  }
  h3 { margin: 28px 0 12px; font-size: 1rem; font-weight: 700; color: var(--muted); }

  .aviso {
    padding: 12px 16px; border-radius: 12px; margin: 12px 0;
    background: var(--sel); border: 2px solid var(--sel-line); font-size: 0.95rem;
  }
  .aviso.erro { background: transparent; border-color: var(--bad); color: var(--bad); }

  /* distros */
  .distros { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (min-width: 640px) { .distros { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
  .distro {
    text-align: left; padding: 16px; background: var(--surface);
    border: 2px solid var(--line); border-radius: 12px; transition: border-color .15s;
  }
  .distro:hover:not(:disabled) { border-color: var(--muted); }
  .distro:disabled { opacity: .55; cursor: not-allowed; }
  .distro strong { display: block; font-size: 1.05rem; }
  .distro span { font-family: var(--mono); font-size: 0.8rem; color: var(--muted); }
  .distro em { display: block; margin-top: 6px; font-style: normal; font-size: 0.8rem; color: var(--ok); font-weight: 500; }
  .distro.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
  .distro.on strong { color: var(--accent); }

  /* busca */
  .search {
    width: 100%; padding: 16px 18px; border-radius: 14px; font: inherit; font-size: 1.15rem;
    border: 2px solid var(--line); background: var(--surface); color: var(--ink);
  }
  .search::placeholder { color: var(--muted); }
  .search:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent); }
  .search:disabled { opacity: .55; }
  .dica { margin: 8px 2px 0; color: var(--muted); font-size: 0.9rem; }
  .vazio { color: var(--muted); padding: 20px 0; }

  /* resultados */
  .lista { display: grid; gap: 8px; }
  .row {
    display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 16px; align-items: center;
    text-align: left; padding: 12px 16px;
    background: var(--surface); border: 2px solid var(--line); border-radius: 12px;
    transition: border-color .15s, background .15s;
  }
  .row:hover:not(:disabled) { border-color: var(--muted); }
  .row:disabled { cursor: default; opacity: .6; }
  .row .rt { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
  .row .rt strong { font-size: 1.02rem; overflow-wrap: anywhere; }
  .row .rt small { font-family: var(--mono); font-size: 0.74rem; color: var(--muted); overflow-wrap: anywhere; }
  .row .rs {
    grid-column: 1; color: var(--muted); font-size: 0.9rem;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .row .mk {
    grid-column: 2; grid-row: 1 / span 2; font-weight: 700; font-size: 0.9rem;
    color: var(--accent); white-space: nowrap;
  }
  .row.on { background: var(--sel); border-color: var(--sel-line); }
  .row.on .mk { color: var(--sel-line); }

  /* populares */
  .grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
  .tile {
    position: relative; display: flex; align-items: center; gap: 12px;
    text-align: left; padding: 12px 40px 12px 14px;
    background: var(--surface); border: 2px solid var(--line); border-radius: 12px;
    transition: border-color .15s, background .15s;
  }
  .tile:hover:not(:disabled) { border-color: var(--muted); }
  .tile:disabled { cursor: default; opacity: .6; }
  .tile .ico { font-size: 1.6rem; line-height: 1; }
  .tile .nm { display: block; font-weight: 700; line-height: 1.2; }
  .tile .tag { display: block; font-family: var(--mono); font-size: 0.74rem; color: var(--muted); }
  .tile.on { background: var(--sel); border-color: var(--sel-line); }
  .tile .check { position: absolute; top: 50%; right: 12px; transform: translateY(-50%); font-weight: 800; color: var(--sel-line); }

  /* painel */
  .painel {
    background: var(--surface); border: 2px solid var(--line);
    border-radius: 16px; padding: 20px;
  }
  @media (min-width: 1000px) { .painel { position: sticky; top: 16px; } }
  .painel h2 { margin-bottom: 8px; }
  .resumo { margin: 0 0 14px; color: var(--muted); }

  .itens { list-style: none; margin: 0 0 16px; padding: 0; max-height: 260px; overflow: auto; }
  .itens li {
    display: flex; align-items: center; gap: 10px; padding: 8px 4px;
    border-bottom: 1px solid var(--line);
  }
  .itens li:last-child { border-bottom: 0; }
  .itens .in { flex: 1; min-width: 0; overflow-wrap: anywhere; font-weight: 500; }
  .itens .in small { display: block; font-family: var(--mono); font-size: 0.72rem; color: var(--muted); font-weight: 400; }
  .itens .x {
    width: 28px; height: 28px; border-radius: 8px; border: 0; background: transparent;
    color: var(--muted); font-size: 1rem; line-height: 1;
  }
  .itens .x:hover { background: var(--bg); color: var(--bad); }
  .st { width: 24px; text-align: center; font-weight: 800; }
  .st.espera { color: var(--muted); }
  .st.rodando { color: var(--accent); display: inline-block; animation: giro 1s linear infinite; }
  .st.ok { color: var(--ok); }
  .st.falhou { color: var(--bad); }
  @keyframes giro { to { transform: rotate(360deg); } }

  .campo { display: block; margin-bottom: 14px; }
  .campo span { display: block; font-weight: 700; margin-bottom: 4px; }
  .campo small { display: block; color: var(--muted); margin-top: 4px; }
  .campo input[type="password"] {
    width: 100%; padding: 10px 14px; border-radius: 10px; font: inherit;
    border: 2px solid var(--line); background: var(--bg); color: var(--ink);
  }
  .opt { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; cursor: pointer; }
  .opt input { width: 18px; height: 18px; accent-color: var(--accent); }
  .nota { margin: 12px 0 0; font-size: 0.88rem; color: var(--muted); }
  .msg-erro { margin: 0 0 14px; color: var(--bad); font-weight: 500; }

  .btn {
    padding: 10px 16px; border-radius: 10px; font-weight: 500;
    background: transparent; border: 2px solid var(--line);
  }
  .btn:hover:not(:disabled) { border-color: var(--muted); }
  .btn:disabled { opacity: .45; cursor: not-allowed; }
  .btn.primary {
    background: var(--accent); border-color: var(--accent); color: var(--accent-ink);
    font-weight: 700; font-size: 1.05rem; padding: 14px 18px; width: 100%;
  }
  .btn.primary:hover:not(:disabled) { filter: brightness(1.08); border-color: var(--accent); }
  .btn.link { border: 0; padding: 4px 0; color: var(--muted); text-decoration: underline; font-size: 0.9rem; }

  .barra { height: 10px; border-radius: 99px; background: var(--bg); overflow: hidden; margin: 6px 0 10px; }
  .barra i { display: block; height: 100%; background: var(--accent); transition: width .3s; }
  .agora { margin: 0 0 12px; font-weight: 500; }

  pre.term {
    margin: 0 0 14px; padding: 14px; border-radius: 10px;
    background: var(--term); color: var(--term-ink);
    font-family: var(--mono); font-size: 0.78rem; line-height: 1.5;
    overflow: auto; height: 260px;
  }
  pre.term .ln { display: block; white-space: pre-wrap; word-break: break-word; }
  pre.term .info { color: #8fb1ff; font-weight: 500; }
  pre.term .good { color: #7fe0a8; }
  pre.term .bad { color: #ff8f99; }
  pre.term .ph { color: var(--term-dim); }

  .resultado { padding: 14px 16px; border-radius: 12px; margin-bottom: 14px; border: 2px solid var(--ok); }
  .resultado.ruim { border-color: var(--bad); }
  .resultado strong { display: block; }
  .resultado.ruim strong { color: var(--bad); }
  .resultado:not(.ruim) strong { color: var(--ok); }

  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; }
    .st.rodando { animation: none; }
  }
</style>
</head>
<body>
<div id="app" class="page" v-cloak>

  <header class="top">
    <h1>Pós-install Linux</h1>
    <p>Procure qualquer programa, monte sua lista e clique em instalar. Tudo acontece aqui, ao vivo.</p>
  </header>

  <div v-if="erroGeral" class="aviso erro">{{ erroGeral }}</div>

  <div v-else-if="estado" class="layout">
    <div>
      <!-- 1. Distro -->
      <section>
        <h2><span class="n">1</span> Qual distro você usa?</h2>
        <div class="distros" role="radiogroup" aria-label="Distro">
          <button v-for="d in estado.distros" :key="d.id"
                  class="distro" :class="{ on: distro === d.id }"
                  role="radio" :aria-checked="distro === d.id"
                  :disabled="fase === 'instalando'"
                  @click="escolherDistro(d.id)">
            <strong>{{ d.nome }}</strong>
            <span>{{ d.sub }}</span>
            <em v-if="estado.detectada === d.id">detectada neste computador</em>
          </button>
        </div>
        <p v-if="estado.detectada && estado.detectada !== distro" class="aviso">
          Este computador parece ser {{ nomeDistro(estado.detectada) }}, mas você escolheu {{ nomeDistro(distro) }}. Os comandos podem falhar.
        </p>
        <p v-if="avisoDistro" class="aviso">{{ avisoDistro }}</p>
      </section>

      <!-- 2. Busca -->
      <section>
        <h2><span class="n">2</span> O que você quer instalar?</h2>

        <input class="search" type="search" v-model="busca" :disabled="fase !== 'escolha'"
               placeholder="Buscar qualquer programa (ex.: onlyoffice, blender, docker, obs)"
               aria-label="Buscar programa" autofocus>
        <p class="dica">Busca ao vivo no Flathub (apps gráficos) e nos repositórios do {{ nomeDistro(distro) }}.</p>

        <!-- resultados da busca -->
        <template v-if="termoValido">
          <p v-if="buscando" class="vazio">Procurando "{{ busca.trim() }}"...</p>
          <p v-for="e in resultados.erros" :key="e" class="aviso">{{ e }}</p>

          <template v-if="resultados.flatpak.length">
            <h3>Apps no Flathub ({{ resultados.flatpak.length }})</h3>
            <div class="lista">
              <button v-for="f in resultados.flatpak" :key="'f' + f.id"
                      class="row" :class="{ on: estaSel('flatpak:' + f.id) }"
                      :disabled="fase !== 'escolha'"
                      @click="alternar({ chave: 'flatpak:' + f.id, nome: f.nome, fonte: 'flatpak' })">
                <span class="rt"><strong>{{ f.nome }}</strong><small>{{ f.id }}</small></span>
                <span class="rs">{{ f.resumo }}</span>
                <span class="mk">{{ estaSel('flatpak:' + f.id) ? '✓ Na lista' : '+ Adicionar' }}</span>
              </button>
            </div>
          </template>

          <template v-if="resultados.repo.length">
            <h3>Pacotes do repositório ({{ resultados.repo.length }})</h3>
            <div class="lista">
              <button v-for="r in resultados.repo" :key="'r' + r.nome"
                      class="row" :class="{ on: estaSel('repo:' + r.nome) }"
                      :disabled="fase !== 'escolha'"
                      @click="alternar({ chave: 'repo:' + r.nome, nome: r.nome, fonte: 'repositório' })">
                <span class="rt"><strong>{{ r.nome }}</strong></span>
                <span class="rs">{{ r.resumo }}</span>
                <span class="mk">{{ estaSel('repo:' + r.nome) ? '✓ Na lista' : '+ Adicionar' }}</span>
              </button>
            </div>
          </template>

          <p v-if="!buscando && !temResultados" class="vazio">
            Nada encontrado para "{{ busca.trim() }}". Tente outro nome ou uma palavra mais curta.
          </p>
        </template>

        <!-- populares (busca vazia) -->
        <template v-else>
          <div v-for="g in grupos" :key="g.cat">
            <h3>Populares: {{ g.cat }}</h3>
            <div class="grid">
              <button v-for="p in g.itens" :key="p.id"
                      class="tile" :class="{ on: estaSel('cat:' + p.id) }"
                      :aria-pressed="estaSel('cat:' + p.id)"
                      :disabled="fase !== 'escolha'"
                      @click="alternar({ chave: 'cat:' + p.id, nome: p.nome, fonte: p.metodos[distro] })">
                <span class="ico" aria-hidden="true">{{ p.icone }}</span>
                <span>
                  <span class="nm">{{ p.nome }}</span>
                  <span class="tag">{{ p.metodos[distro] }}</span>
                </span>
                <span v-if="estaSel('cat:' + p.id)" class="check">✓</span>
              </button>
            </div>
          </div>
        </template>
      </section>
    </div>

    <!-- 3. Lista e instalação -->
    <aside class="painel">
      <h2><span class="n">3</span> {{ fase === 'escolha' ? 'Sua lista' : (fase === 'instalando' ? 'Instalando' : 'Concluído') }}</h2>

      <template v-if="fase === 'escolha'">
        <p v-if="!sel.length" class="resumo">Nada na lista ainda. Busque um programa ou escolha entre os populares.</p>
        <p v-else class="resumo">
          {{ sel.length }} {{ sel.length === 1 ? 'item' : 'itens' }}
          <button class="btn link" @click="limpar">limpar tudo</button>
        </p>
      </template>

      <ul v-if="sel.length" class="itens">
        <li v-for="s in sel" :key="s.chave">
          <span class="in">{{ s.nome }}<small>{{ s.fonte }}</small></span>
          <button v-if="fase === 'escolha'" class="x" @click="remover(s.chave)" :aria-label="'Remover ' + s.nome">✕</button>
          <span v-else class="st" :class="status[s.chave] || 'espera'">{{ simbolo(s.chave) }}</span>
        </li>
      </ul>

      <!-- antes de instalar -->
      <template v-if="fase === 'escolha'">
        <p v-if="estado.ocupado" class="msg-erro">Já existe uma instalação em andamento neste computador. Espere terminar.</p>
        <p v-if="!estado.tem_sudo" class="msg-erro">O sudo não foi encontrado. Rode o servidor como root ou instale o sudo.</p>

        <label v-if="estado.precisa_senha" class="campo">
          <span>Senha do seu usuário (sudo)</span>
          <input type="password" v-model="senha" autocomplete="current-password" @keyup.enter="instalar">
          <small>Fica só na memória do servidor local e não é gravada em lugar nenhum.</small>
        </label>

        <label class="opt">
          <input type="checkbox" v-model="atualizar">
          Atualizar o sistema antes de instalar
        </label>

        <p v-if="erro" class="msg-erro">{{ erro }}</p>

        <button class="btn primary" :disabled="!sel.length || estado.ocupado || !estado.tem_sudo" @click="instalar">
          {{ sel.length ? 'Instalar ' + sel.length + (sel.length === 1 ? ' item' : ' itens') : 'Instalar' }}
        </button>
        <p class="nota">Tudo roda neste computador, pelo servidor que você abriu no terminal.</p>
      </template>

      <!-- durante e depois -->
      <template v-else>
        <div class="barra" role="progressbar" :aria-valuenow="feitos" aria-valuemin="0" :aria-valuemax="total">
          <i :style="{ width: (total ? (feitos / total) * 100 : 0) + '%' }"></i>
        </div>
        <p class="agora" v-if="fase === 'instalando'">
          {{ atual ? atual : 'Preparando...' }} ({{ feitos }} de {{ total }})
        </p>

        <div v-if="fase === 'fim'" class="resultado" :class="{ ruim: falhas.length || semFim }">
          <strong v-if="semFim">A conexão com o servidor foi interrompida.</strong>
          <strong v-else-if="!falhas.length">Tudo instalado.</strong>
          <strong v-else>{{ falhas.length }} {{ falhas.length === 1 ? 'item falhou' : 'itens falharam' }}.</strong>
          <span v-if="falhas.length">{{ falhas.join(', ') }}. Veja o registro abaixo.</span>
          <span v-else-if="!semFim">Reinicie a sessão para os apps aparecerem no menu e o grupo docker valer.</span>
        </div>

        <pre ref="logEl" class="term"><code>
          <span v-for="(l, i) in log" :key="i" class="ln" :class="l.k">{{ l.m }}</span>
          <span v-if="!log.length" class="ln ph">Aguardando saída...</span>
        </code></pre>

        <button v-if="fase === 'fim'" class="btn primary" @click="voltar">Voltar e instalar mais</button>
      </template>
    </aside>
  </div>

  <p v-else class="vazio">Conectando ao servidor local...</p>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js"></script>
<script>
const { createApp, ref, computed, watch, nextTick, onMounted } = Vue;

const TOKEN = new URLSearchParams(location.search).get('t') || '';
const NOMES_ETAPA = { _update: 'o sistema', _flatpak: 'o Flatpak' };
const VAZIO = () => ({ repo: [], flatpak: [], erros: [] });

createApp({
  setup() {
    const estado = ref(null);
    const erroGeral = ref('');
    const distro = ref('apt');
    const sel = ref([]);               // [{ chave, nome, fonte }]
    const busca = ref('');
    const atualizar = ref(true);
    const senha = ref('');
    const erro = ref('');
    const avisoDistro = ref('');

    const resultados = ref(VAZIO());
    const buscando = ref(false);

    const fase = ref('escolha');       // escolha | instalando | fim
    const status = ref({});            // chave -> espera | rodando | ok | falhou
    const log = ref([]);
    const atual = ref('');
    const ordem = ref([]);
    const semFim = ref(false);
    const logEl = ref(null);

    const api = (url, opcoes = {}) => fetch(url, {
      ...opcoes,
      headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    });

    /* ---------- início ---------- */
    onMounted(async () => {
      if (!TOKEN) {
        erroGeral.value = 'Abra esta página pelo endereço mostrado no terminal (ele inclui um código de acesso).';
        return;
      }
      try {
        const r = await api('/api/estado');
        const dados = await r.json();
        if (!r.ok) { erroGeral.value = dados.erro || 'Não consegui falar com o servidor.'; return; }

        distro.value = dados.detectada || 'apt';
        try {
          const salvo = JSON.parse(localStorage.getItem('pos-install-local-v2') || 'null');
          if (salvo) {
            if (!dados.detectada && dados.distros.some(d => d.id === salvo.distro)) distro.value = salvo.distro;
            if (Array.isArray(salvo.sel)) {
              sel.value = salvo.sel.filter(s => s && typeof s.chave === 'string' && typeof s.nome === 'string'
                && (!s.chave.startsWith('cat:') || dados.catalogo.some(p => 'cat:' + p.id === s.chave))
                && (!s.chave.startsWith('repo:') || salvo.distro === distro.value));
            }
            if (typeof salvo.atualizar === 'boolean') atualizar.value = salvo.atualizar;
          }
        } catch (e) { /* sem armazenamento: segue sem salvar */ }
        estado.value = dados;
      } catch (e) {
        erroGeral.value = 'O servidor local não respondeu. Ele ainda está rodando no terminal?';
      }
    });

    watch([distro, sel, atualizar], () => {
      try {
        localStorage.setItem('pos-install-local-v2', JSON.stringify({
          distro: distro.value, sel: sel.value, atualizar: atualizar.value,
        }));
      } catch (e) { /* ignora */ }
    }, { deep: true });

    /* ---------- busca ao vivo ---------- */
    let timer = null;
    let seq = 0;
    const termoValido = computed(() => busca.value.trim().length >= 2);
    const temResultados = computed(() => resultados.value.flatpak.length > 0 || resultados.value.repo.length > 0);

    const buscar = async (q) => {
      const meu = ++seq;
      try {
        const r = await api('/api/buscar?q=' + encodeURIComponent(q) + '&distro=' + encodeURIComponent(distro.value));
        const dados = await r.json();
        if (meu !== seq) return;                       // chegou uma busca mais nova
        resultados.value = r.ok ? { ...VAZIO(), ...dados } : { ...VAZIO(), erros: [dados.erro || 'Erro na busca.'] };
      } catch (e) {
        if (meu === seq) resultados.value = { ...VAZIO(), erros: ['Não consegui falar com o servidor local.'] };
      } finally {
        if (meu === seq) buscando.value = false;
      }
    };

    const agendarBusca = () => {
      clearTimeout(timer);
      const q = busca.value.trim();
      if (q.length < 2) { seq++; buscando.value = false; resultados.value = VAZIO(); return; }
      buscando.value = true;
      timer = setTimeout(() => buscar(q), 400);
    };
    watch(busca, agendarBusca);

    const escolherDistro = (id) => {
      if (id === distro.value) return;
      distro.value = id;
      const antes = sel.value.length;
      sel.value = sel.value.filter(s => !s.chave.startsWith('repo:'));   // nomes de pacote dependem da distro
      avisoDistro.value = sel.value.length < antes
        ? 'Os pacotes de repositório foram tirados da lista, porque os nomes mudam de distro para distro. Busque de novo.'
        : '';
      agendarBusca();
    };

    /* ---------- populares ---------- */
    const grupos = computed(() => {
      const mapa = new Map();
      (estado.value ? estado.value.catalogo : []).forEach(p => {
        if (!mapa.has(p.cat)) mapa.set(p.cat, []);
        mapa.get(p.cat).push(p);
      });
      return [...mapa].map(([cat, itens]) => ({ cat, itens }));
    });

    const nomeDistro = (id) => ((estado.value && estado.value.distros.find(d => d.id === id)) || {}).nome || id;

    /* ---------- lista ---------- */
    const estaSel = (chave) => sel.value.some(s => s.chave === chave);
    const alternar = (item) => {
      sel.value = estaSel(item.chave)
        ? sel.value.filter(s => s.chave !== item.chave)
        : [...sel.value, item];
    };
    const remover = (chave) => { sel.value = sel.value.filter(s => s.chave !== chave); };
    const limpar = () => { sel.value = []; };

    /* ---------- progresso ---------- */
    const nomePrograma = (chave) =>
      NOMES_ETAPA[chave] || ((sel.value.find(s => s.chave === chave) || {}).nome) || chave;
    const simbolo = (chave) => ({ espera: '…', rodando: '↻', ok: '✓', falhou: '✕' }[status.value[chave] || 'espera']);

    const total = computed(() => ordem.value.length);
    const feitos = computed(() => ordem.value.filter(c => ['ok', 'falhou'].includes(status.value[c])).length);
    const falhas = computed(() =>
      Object.keys(status.value).filter(c => status.value[c] === 'falhou').map(nomePrograma));

    const escrever = (m, k = '') => {
      log.value.push({ m, k });
      if (log.value.length > 3000) log.value.splice(0, 500);
      nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight; });
    };

    const tratar = (ev) => {
      if (ev.t === 'log') return escrever(ev.m);
      if (ev.t === 'start') {
        status.value[ev.id] = 'rodando';
        atual.value = (ev.id.startsWith('_') ? 'Preparando ' : 'Instalando ') + nomePrograma(ev.id);
        return escrever('▶ ' + atual.value, 'info');
      }
      if (ev.t === 'ok') {
        status.value[ev.id] = 'ok';
        return escrever('✓ ' + nomePrograma(ev.id) + ' concluído', 'good');
      }
      if (ev.t === 'fail') {
        status.value[ev.id] = 'falhou';
        return escrever('✕ Falhou: ' + nomePrograma(ev.id), 'bad');
      }
      if (ev.t === 'fim') {
        semFim.value = false;
        fase.value = 'fim';
      }
    };

    /* ---------- instalar ---------- */
    const instalar = async () => {
      erro.value = '';
      if (!sel.value.length) return;
      if (estado.value.precisa_senha && !senha.value) { erro.value = 'Digite a senha do sudo.'; return; }

      const chaves = sel.value.map(s => s.chave);
      let r;
      try {
        r = await api('/api/instalar', {
          method: 'POST',
          body: JSON.stringify({ distro: distro.value, itens: chaves, atualizar: atualizar.value, senha: senha.value }),
        });
      } catch (e) { erro.value = 'Não consegui falar com o servidor local.'; return; }

      if (!r.ok) {
        const dados = await r.json().catch(() => ({}));
        erro.value = dados.erro || 'Não foi possível iniciar a instalação.';
        return;
      }

      senha.value = '';
      ordem.value = chaves;
      status.value = {};
      chaves.forEach(c => { status.value[c] = 'espera'; });
      log.value = [];
      atual.value = '';
      semFim.value = true;     // vira false quando chegar o evento "fim"
      fase.value = 'instalando';

      const leitor = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      try {
        while (true) {
          const { done, value } = await leitor.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf('\n')) >= 0) {
            const linha = buf.slice(0, i).trim();
            buf = buf.slice(i + 1);
            if (linha) tratar(JSON.parse(linha));
          }
        }
      } catch (e) { /* conexão caiu: tratado abaixo */ }
      if (fase.value !== 'fim') fase.value = 'fim';
    };

    const voltar = async () => {
      fase.value = 'escolha';
      erro.value = '';
      try {
        const r = await api('/api/estado');
        if (r.ok) estado.value = await r.json();
      } catch (e) { /* mantém o estado anterior */ }
    };

    return {
      estado, erroGeral, distro, sel, busca, atualizar, senha, erro, avisoDistro,
      resultados, buscando, termoValido, temResultados,
      fase, status, log, atual, semFim, logEl,
      grupos, nomeDistro, escolherDistro, estaSel, alternar, remover, limpar,
      simbolo, total, feitos, falhas, instalar, voltar,
    };
  },
}).mount('#app');
</script>
</body>
</html>
'''

# ======================================================================
#  Funções auxiliares
# ======================================================================

def detectar_distro():
    """Tenta descobrir a família da distro lendo /etc/os-release."""
    dados = {}
    try:
        for linha in Path("/etc/os-release").read_text().splitlines():
            if "=" in linha:
                chave, valor = linha.split("=", 1)
                dados[chave] = valor.strip('"')
    except OSError:
        return None
    texto = (dados.get("ID", "") + " " + dados.get("ID_LIKE", "")).lower()
    if "ubuntu" in texto or "debian" in texto:
        return "apt"
    if "fedora" in texto or "rhel" in texto:
        return "dnf"
    if "arch" in texto:
        return "pacman"
    if "suse" in texto:
        return "zypper"
    return None


def eh_root():
    return os.geteuid() == 0


def sudo_precisa_senha():
    if eh_root():
        return False
    if not shutil.which("sudo"):
        return False
    return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0


def metodo(spec):
    if spec.startswith("flatpak:"):
        return "flatpak"
    if spec.startswith("cmd:"):
        return "comando"
    return "repositório"


# ----------------------------------------------------------------------
#  Itens escolhidos pelo usuário. Formato das chaves:
#    cat:ID          programa do catálogo "populares"
#    repo:pacote     pacote do repositório da distro (vindo da busca)
#    flatpak:app.id  app do Flathub (vindo da busca)
# ----------------------------------------------------------------------

RE_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._:@-]{0,127}")
RE_FLATPAK = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+")


def validar_item(chave):
    if not isinstance(chave, str) or len(chave) > 220:
        return False
    tipo, _, valor = chave.partition(":")
    if tipo == "cat":
        return valor in POR_ID
    if tipo == "repo":
        return RE_REPO.fullmatch(valor) is not None
    if tipo == "flatpak":
        return RE_FLATPAK.fullmatch(valor) is not None and len(valor) <= 200
    return False


def comando_do_item(distro_id, chave):
    """Devolve (comando, usa_flatpak)."""
    d = DISTROS[distro_id]
    tipo, _, valor = chave.partition(":")
    if tipo == "cat":
        spec = POR_ID[valor]["pkg"][distro_id]
        if spec.startswith("flatpak:"):
            return "flatpak install -y flathub " + spec[len("flatpak:"):], True
        if spec.startswith("cmd:"):
            return spec[len("cmd:"):], False
        return d["install"] + " " + spec, False
    if tipo == "repo":
        return d["install"] + " " + shlex.quote(valor), False
    return "flatpak install -y flathub " + shlex.quote(valor), True


def montar_script(distro_id, itens, atualizar):
    """Gera o script bash. Cada etapa imprime marcadores @@START/@@OK/@@FAIL
    que o servidor traduz em eventos para a página."""
    d = DISTROS[distro_id]
    linhas = ["export DEBIAN_FRONTEND=noninteractive", ""]

    def etapa(etapa_id, comando):
        linhas.append('echo "@@START|%s"' % etapa_id)
        linhas.append('if %s; then echo "@@OK|%s"; else echo "@@FAIL|%s"; fi' % (comando, etapa_id, etapa_id))
        linhas.append("")

    comandos = [(chave,) + comando_do_item(distro_id, chave) for chave in itens]

    if atualizar:
        etapa("_update", d["update"])

    if any(usa_flatpak for _, _, usa_flatpak in comandos):
        etapa("_flatpak",
              "( command -v flatpak >/dev/null 2>&1 || %s flatpak ) && "
              "flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"
              % d["install"])

    for chave, cmd, _ in comandos:
        etapa(chave, cmd)

    return "\n".join(linhas)


# ----------------------------------------------------------------------
#  Busca ao vivo: repositórios da distro + Flathub
# ----------------------------------------------------------------------

def sanitizar_busca(q):
    q = re.sub(r"[^\w .+\-]", " ", q or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", q).strip()[:60]


def rodar(cmd, timeout=25):
    """Roda um comando de leitura (sem shell) e devolve a saída de texto."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           env=dict(os.environ, LC_ALL="C"))
        return r.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_apt(texto):
    res = []
    for linha in texto.splitlines():
        nome, sep, resumo = linha.partition(" - ")
        if sep and RE_REPO.fullmatch(nome.strip()):
            res.append({"nome": nome.strip(), "resumo": resumo.strip()})
    return res


ARQUITETURAS = {"x86_64", "noarch", "i686", "i386", "aarch64", "ppc64le", "s390x", "armv7hl", "src"}


def parse_dnf(texto):
    res, vistos = [], set()
    for linha in texto.splitlines():
        if not linha.strip() or linha.lstrip().startswith(("=", "Matched", "Last metadata", "Updating")):
            continue
        m = re.match(r"^\s*(\S+)\s+(?::\s+)?(.*)$", linha)
        if not m or "." not in m.group(1):
            continue
        nome, _, arq = m.group(1).rpartition(".")
        if arq in ARQUITETURAS and nome not in vistos and RE_REPO.fullmatch(nome):
            vistos.add(nome)
            res.append({"nome": nome, "resumo": m.group(2).strip()})
    return res


def parse_pacman(texto):
    res, atual = [], None
    for linha in texto.splitlines():
        if linha and not linha[0].isspace():
            primeiro = linha.split()[0]
            if "/" in primeiro:
                nome = primeiro.split("/", 1)[1]
                atual = {"nome": nome, "resumo": ""} if RE_REPO.fullmatch(nome) else None
                if atual:
                    res.append(atual)
        elif atual is not None and not atual["resumo"]:
            atual["resumo"] = linha.strip()
    return res


def parse_zypper(texto):
    res, vistos = [], set()
    for linha in texto.splitlines():
        partes = [p.strip() for p in linha.split("|")]
        if len(partes) >= 4 and partes[1] not in ("Name", "") and RE_REPO.fullmatch(partes[1]) \
                and partes[1] not in vistos:
            vistos.add(partes[1])
            res.append({"nome": partes[1], "resumo": partes[2]})
    return res


def ordenar_por_nome(itens, q):
    """Nome igual vem primeiro, depois começa com, depois contém todas as palavras,
    depois contém alguma; quem só casou na descrição fica no fim (ordem original)."""
    ql = q.lower()
    termos = ql.split()
    junto = ql.replace(" ", "")

    def pontos(it):
        n = it["nome"].lower()
        if n in (ql, junto):
            return 0
        if n.startswith(ql) or n.startswith(junto):
            return 1
        if ql in n or junto in n or all(t in n for t in termos):
            return 2
        if any(t in n for t in termos):
            return 3
        return 4

    def chave(it):
        p = pontos(it)
        return (p, len(it["nome"]) if p < 4 else 0, it["nome"] if p < 4 else "")

    return sorted(itens, key=chave)


def _busca_repo_termos(distro, termos):
    if distro == "apt":
        if not shutil.which("apt-cache"):
            return []
        return parse_apt(rodar(["apt-cache", "search"] + termos))
    if distro == "dnf":
        if not shutil.which("dnf"):
            return []
        return parse_dnf(rodar(["dnf", "-q", "search"] + termos, timeout=90))
    if distro == "pacman":
        if not shutil.which("pacman"):
            return []
        regex = [t.replace(".", r"\.").replace("+", r"\+") for t in termos]
        return parse_pacman(rodar(["pacman", "-Ss"] + regex))
    if not shutil.which("zypper"):
        return []
    return parse_zypper(rodar(["zypper", "-n", "--no-refresh", "search", "--type", "package"] + termos, timeout=60))


def busca_repo(distro, q):
    termos = q.split()
    lista = _busca_repo_termos(distro, termos)
    if len(termos) > 1:  # "libre office" também deve achar "libreoffice"
        vistos = {it["nome"] for it in lista}
        lista += [it for it in _busca_repo_termos(distro, ["".join(termos)]) if it["nome"] not in vistos]
    return ordenar_por_nome(lista, q)[:50]


def busca_flathub(q):
    """Devolve (lista, aviso). Usa a API pública do Flathub; se falhar, tenta o flatpak local."""
    aviso = ""
    try:
        req = urllib.request.Request(
            "https://flathub.org/api/v2/search",
            data=json.dumps({"query": q, "filters": []}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "pos-install-linux"})
        with urllib.request.urlopen(req, timeout=15) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        res = []
        for h in dados.get("hits", []):
            app_id = str(h.get("app_id") or h.get("id") or "").strip()
            if RE_FLATPAK.fullmatch(app_id):
                res.append({"id": app_id, "nome": str(h.get("name") or app_id),
                            "resumo": str(h.get("summary") or "")})
        return res[:40], aviso
    except Exception as e:  # rede, certificado, formato inesperado...
        aviso = "Não consegui consultar o Flathub (%s)." % (str(e)[:80] or type(e).__name__)

    if shutil.which("flatpak"):
        saida = rodar(["flatpak", "search", "--columns=application,name,description", q], timeout=30)
        res = []
        for linha in saida.splitlines():
            p = linha.split("\t")
            if len(p) >= 2 and RE_FLATPAK.fullmatch(p[0].strip()):
                res.append({"id": p[0].strip(), "nome": p[1].strip() or p[0].strip(),
                            "resumo": p[2].strip() if len(p) > 2 else ""})
        if res:
            return res[:40], ""
    return [], aviso


def buscar_tudo(distro, q):
    saida = {"repo": [], "flatpak": [], "erros": []}

    def t_repo():
        try:
            saida["repo"] = busca_repo(distro, q)
        except Exception as e:
            saida["erros"].append("Erro ao buscar nos repositórios: %s" % e)

    def t_flat():
        try:
            saida["flatpak"], aviso = busca_flathub(q)
            if aviso:
                saida["erros"].append(aviso)
        except Exception as e:
            saida["erros"].append("Erro ao buscar no Flathub: %s" % e)

    fios = [threading.Thread(target=t_repo), threading.Thread(target=t_flat)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    return saida


lock = threading.Lock()  # só uma instalação por vez

# ======================================================================
#  Servidor HTTP
# ======================================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "PosInstall"

    def log_message(self, *args):  # silencia o log de acessos
        pass

    # ---- utilidades ----
    def _host_ok(self):
        porta = self.server.server_port
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % porta, "localhost:%d" % porta)

    def _token_ok(self):
        return secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def _json(self, codigo, obj):
        corpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    # ---- GET ----
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"erro": "Host inválido."})
        rota = self.path.split("?")[0]

        if rota == "/":
            corpo = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)
            return

        if rota == "/api/estado":
            if not self._token_ok():
                return self._json(403, {"erro": "Token inválido. Abra pelo endereço mostrado no terminal."})
            catalogo = [
                {"id": p["id"], "cat": p["cat"], "icone": p["icone"], "nome": p["nome"],
                 "metodos": {d: metodo(p["pkg"][d]) for d in DISTROS}}
                for p in CATALOGO
            ]
            return self._json(200, {
                "distros": [{"id": k, "nome": v["nome"], "sub": v["sub"]} for k, v in DISTROS.items()],
                "catalogo": catalogo,
                "detectada": detectar_distro(),
                "precisa_senha": sudo_precisa_senha(),
                "tem_sudo": eh_root() or bool(shutil.which("sudo")),
                "root": eh_root(),
                "ocupado": lock.locked(),
            })

        if rota == "/api/buscar":
            if not self._token_ok():
                return self._json(403, {"erro": "Token inválido."})
            params = parse_qs(urlparse(self.path).query)
            q = sanitizar_busca((params.get("q") or [""])[0])
            distro = (params.get("distro") or [""])[0]
            if distro not in DISTROS:
                distro = detectar_distro() or "apt"
            if len(q) < 2:
                return self._json(200, {"repo": [], "flatpak": [], "erros": []})
            return self._json(200, buscar_tudo(distro, q))

        self._json(404, {"erro": "Não encontrado."})

    # ---- POST ----
    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"erro": "Host inválido."})
        if not self._token_ok():
            return self._json(403, {"erro": "Token inválido."})
        if self.path.split("?")[0] != "/api/instalar":
            return self._json(404, {"erro": "Não encontrado."})

        # --- lê e valida o pedido (só IDs, nunca comandos) ---
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > 100_000:
                return self._json(413, {"erro": "Pedido grande demais."})
            dados = json.loads(self.rfile.read(tamanho) or b"{}")
            distro = dados["distro"]
            itens = dados["itens"]
            atualizar = bool(dados.get("atualizar"))
            senha = str(dados.get("senha") or "")[:256]
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"erro": "Pedido inválido."})

        if distro not in DISTROS:
            return self._json(400, {"erro": "Distro desconhecida."})
        if not isinstance(itens, list) or not itens or len(itens) > 300 or not all(validar_item(i) for i in itens):
            return self._json(400, {"erro": "Lista de programas inválida."})
        itens = list(dict.fromkeys(itens))  # remove duplicados mantendo a ordem

        if not eh_root() and not shutil.which("sudo"):
            return self._json(400, {"erro": "O comando sudo não foi encontrado neste sistema."})

        if not lock.acquire(blocking=False):
            return self._json(409, {"erro": "Já existe uma instalação em andamento."})

        try:
            # --- permissão de administrador ---
            if eh_root():
                prefixo, usar_senha = [], False
            elif sudo_precisa_senha():
                if not senha:
                    return self._json(400, {"erro": "Digite a senha do sudo."})
                subprocess.run(["sudo", "-k"], capture_output=True)  # ignora credenciais em cache
                teste = subprocess.run(["sudo", "-S", "-p", "", "-v"], input=(senha + "\n").encode(),
                                       capture_output=True, timeout=30)
                if teste.returncode != 0:
                    return self._json(403, {"erro": "Senha incorreta."})
                prefixo, usar_senha = ["sudo", "-S", "-p", ""], True
            else:
                prefixo, usar_senha = ["sudo", "-n"], False

            script = montar_script(distro, itens, atualizar)

            # --- começa a transmitir o progresso ---
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()

            conectado = True

            def emitir(obj):
                nonlocal conectado
                if not conectado:
                    return
                try:
                    self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                    self.wfile.flush()
                except OSError:
                    conectado = False  # navegador fechou: a instalação continua até o fim

            proc = subprocess.Popen(
                prefixo + ["env", "DEBIAN_FRONTEND=noninteractive", "bash", "-c", script],
                stdin=subprocess.PIPE if usar_senha else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            if usar_senha:
                proc.stdin.write((senha + "\n").encode())
                proc.stdin.close()
            senha = ""

            for bruto in iter(proc.stdout.readline, b""):
                linha = bruto.decode("utf-8", "replace").rstrip("\r\n")
                if linha.startswith("@@"):
                    tipo, _, etapa_id = linha[2:].partition("|")
                    emitir({"t": tipo.lower(), "id": etapa_id})
                elif linha:
                    emitir({"t": "log", "m": linha})

            emitir({"t": "fim", "codigo": proc.wait()})
        except subprocess.TimeoutExpired:
            if not self.wfile.closed:
                self._json(504, {"erro": "O sudo demorou demais para responder."})
        finally:
            lock.release()


def main():
    if eh_root():
        print("Aviso: você está rodando como root. O ideal é rodar como usuário normal.\n")

    porta = PORTA_INICIAL
    while True:
        try:
            servidor = ThreadingHTTPServer((HOST, porta), Handler)
            break
        except OSError:
            porta += 1
            if porta > PORTA_INICIAL + 20:
                sys.exit("Não consegui abrir uma porta livre.")

    url = "http://127.0.0.1:%d/?t=%s" % (porta, TOKEN)
    print("Pós-install Linux rodando.")
    print("Abra no navegador:  " + url)
    print("Para encerrar, aperte Ctrl+C.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
