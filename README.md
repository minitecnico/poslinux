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
