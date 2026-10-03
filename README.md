Agora é só pegar o endereço do arquivo e rodar o comando.

## 1. Pegar o endereço certo
1. No GitHub, abra o repositório e clique no arquivo `pos-install.py`.
2. Clique no botão **Raw**, no canto superior direito do arquivo.
3. Copie o endereço da barra do navegador. Ele vai ser parecido com:
   ```
   http://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install.py

   ```

Copiando daí você não corre o risco de errar o usuário, o nome do repositório ou a branch.

## 2. Rodar
Abra o terminal (`Ctrl + Alt + T`) e cole o comando, trocando pelo seu endereço:

```bash

http://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install.py
```

Se der `curl: command not found`, use:
```bash
wget -qO- http://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install.py | python3 -
```

## 3. Usar a página
1. O navegador abre sozinho com a página. Se não abrir, copie o endereço que o terminal mostra (termina com `?t=...`) e cole no navegador.
2. Confira se a distro detectada está certa.
3. Marque os programas.
4. Digite a senha do sudo na própria página.
5. Clique em **Instalar** e acompanhe pela barra e pelo log.

Quando terminar, volte ao terminal e aperte `Ctrl + C` para encerrar o servidor.

## Se der erro
- **`404: Not Found` no terminal:** o endereço está errado, ou o repositório não é Public. Refaça o passo 1.
- **`python3: command not found`:** instale o Python, por exemplo com `sudo apt install python3` no Ubuntu.
- **Nada abre no navegador:** copie manualmente o endereço que aparece no terminal.
----------------------------------------------------------------------------

http://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install.py

################################################################################################################################################################
################################################################################################################################################################

# Pós-install Windows

Instale todos os seus programas de uma vez em um Windows recém-formatado: procure, monte a lista, clique em **Instalar** e acompanhe tudo ao vivo no navegador.

Usa o **winget**, o instalador oficial da Microsoft, que tem milhares de programas (Chrome, VS Code, OnlyOffice, Docker, 7-Zip, Steam e muito mais).

## Como usar

1. Abra o **PowerShell** (menu Iniciar, digite `PowerShell`).
2. Cole o comando abaixo e aperte Enter:

```powershell
irm https://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install-windows.ps1 | iex
```

3. O Windows vai mostrar uma janela pedindo permissão de administrador. Clique em **Sim**.
4. O navegador abre com a página. Procure os programas, adicione à lista e clique em **Instalar**.

Para encerrar, feche a janela do PowerShell.

> Dica: guarde o comando nas notas do celular ou em um e-mail para si mesmo. É só ele que você precisa lembrar.

## O que você vai ver

| Parte da página | Para que serve |
|---|---|
| **Busca** | Procura ao vivo em todo o catálogo do winget. Digite `onlyoffice`, `blender`, `obs`... |
| **Populares** | Atalhos para 46 programas comuns, aparecem quando a busca está vazia. |
| **Sua lista** | Tudo que você marcou. Dá para misturar populares e resultados da busca e remover itens com o ✕. |
| **Instalar** | Instala um por um. Cada item mostra ✓ (ok) ou ✕ (falhou), com barra de progresso e o registro do winget. |
| **Atualizar os programas já instalados** | Opcional. Roda `winget upgrade --all` antes de instalar. Vem desmarcado. |

Se um programa já estiver instalado, ele aparece como ✓ com a observação "já instalado", não como erro.

## Requisitos

- Windows 10 (versão 1809 ou mais nova) ou Windows 11.
- **winget** instalado. Windows 11 e Windows 10 atualizado já vêm com ele. Se não tiver, abra a Microsoft Store, procure por **Instalador de Aplicativo** (App Installer) e atualize. A própria página avisa quando o winget não é encontrado.
- Conexão com a internet (a página carrega o Vue e as fontes de servidores externos, e o winget baixa os programas).
- Um navegador (o Edge que já vem no Windows serve).

Você **não** precisa instalar Python, Node ou qualquer outra coisa.

## Segurança

Como o programa instala coisas com permissão de administrador, ele foi feito com cuidado:

- **Só aceita conexões do próprio computador** (`127.0.0.1`). Ninguém na sua rede acessa.
- **Exige um código de acesso aleatório**, que vai no endereço aberto pelo programa. Outros sites abertos no navegador não conseguem mandar comandos para ele.
- **A página nunca envia comandos.** Ela só envia o ID de um programa (por exemplo `VideoLAN.VLC`). Esse ID passa por validação estrita e é entregue ao winget como argumento, nunca montado como texto de comando.
- **Uma instalação por vez.**
- Nada é gravado em disco além do que o winget instala, e nenhuma informação sua é enviada para fora.
- O arquivo é texto puro. Dá para abrir e ler o que ele faz antes de rodar.

## Solução de problemas

| Problema | O que fazer |
|---|---|
| `404` ou erro ao baixar o script | Confira se o arquivo se chama exatamente `pos-install-windows.ps1`, se está na raiz do repositório e se o repositório é **Público**. |
| Erro de SSL/TLS ao rodar o `irm` (Windows 10 antigo) | Rode antes: `[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12` e depois o comando de sempre. |
| A janela de administrador não apareceu | O programa segue sem administrador. Funciona, mas o Windows vai pedir confirmação em várias instalações. Para ter tudo automático, abra o PowerShell com **botão direito, Executar como administrador**, e rode o comando. |
| O navegador não abriu | Copie o endereço que o PowerShell mostra (`http://127.0.0.1:8765/?t=...`) e cole no navegador. Ele precisa ter o `?t=...` no final. |
| A página diz que o winget não foi encontrado | Atualize o **Instalador de Aplicativo** na Microsoft Store e rode de novo. |
| A busca não retorna nada | Confira a internet e tente uma palavra mais curta. Se continuar vazio com nomes que existem, rode `winget search vlc` no PowerShell e veja se ele funciona fora do programa. |
| Um item deu ✕ | Leia o registro na própria página. Causas comuns: o programa está aberto, o instalador pede reinicialização, ou o ID mudou. Procure o nome na busca para achar o ID atual. |
| A porta já está em uso | O programa tenta sozinho as portas seguintes (8766, 8767...) e mostra o endereço certo. |
| O antivírus reclamou | O script é texto aberto e só chama o winget. Se preferir, leia o arquivo antes de rodar. |

Alguns programas só aparecem no menu Iniciar depois de reiniciar o computador.

## Personalizar

### Se você renomear o arquivo

Quando o programa não está como administrador, ele se reabre sozinho como administrador baixando o próprio script de novo. O endereço usado para isso está no começo do arquivo, na linha `$UrlScript`. Se você mudar o nome do arquivo, o usuário ou o repositório, atualize essa linha.

### Adicionar um programa à lista de populares

Os populares ficam codificados dentro do arquivo (assim ele continua em ASCII puro e não quebra os acentos no Windows). Para adicionar um, rode este script no PowerShell, na pasta onde o arquivo está, trocando a linha do `winget` pelo programa que você quer:

```powershell
$arquivo = 'pos-install-windows.ps1'
$texto = Get-Content $arquivo -Raw
$m = [regex]::Match($texto, "\`$DadosB64 = '([^']+)'")
$dados = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($m.Groups[1].Value)) | ConvertFrom-Json

# --- edite aqui ---
$dados.catalogo += [pscustomobject]@{ id = 'gimp'; cat = 'Escritório e mídia'; icone = '🎨'; nome = 'GIMP'; winget = 'GIMP.GIMP.3' }
# ------------------

$novo = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($dados | ConvertTo-Json -Depth 5 -Compress)))
$texto.Replace($m.Groups[1].Value, $novo) | Set-Content $arquivo -Encoding Ascii -NoNewline
```

Para descobrir o ID do winget de um programa, use `winget search nome` ou a própria busca da página. Depois, envie o arquivo atualizado para o GitHub.

Você não precisa fazer isso para instalar qualquer programa: a busca já encontra tudo que existe no winget. A lista de populares é só um atalho.

## Como funciona

O comando baixa o script e o executa na memória. O script:

1. Pede permissão de administrador, se ainda não tiver.
2. Abre um pequeno servidor web **somente local**, com um código de acesso aleatório.
3. Abre o navegador na página, que conversa com esse servidor.
4. A busca roda `winget search`, e a instalação roda `winget install` para cada item, enviando o progresso para a página em tempo real.

Tudo isso usa só o que já vem no Windows (PowerShell e winget).

## Limitações

- Instala apenas o que existe no repositório **winget**. Programas que não estão lá precisam ser instalados à mão.
- Alguns instaladores não têm modo silencioso e podem abrir a própria janela.
- Os IDs do winget às vezes mudam. Se um popular falhar, procure pelo nome na busca para achar o ID atual.
- Não há botão de cancelar. Interromper um instalador no meio pode deixar o programa pela metade, por isso a página não oferece isso. Se fechar a aba, a instalação em andamento continua até terminar.

## Usa Linux?

Existe uma versão equivalente para Linux (Ubuntu, Fedora, Arch e openSUSE), com busca ao vivo no Flathub e nos repositórios da distro:

```bash
curl -fsSL https://raw.githubusercontent.com/minitecnico/poslinux/refs/heads/main/pos-install.py | python3 -
```


